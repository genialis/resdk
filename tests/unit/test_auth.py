"""Unit tests for bearer-token / Auth0 authentication."""

import base64
import copy
import io
import json
import socket
import threading
import time
import unittest
import urllib.parse
from unittest.mock import MagicMock, patch

import requests

from resdk import auth
from resdk.resolwe import ResAuth, Resolwe, _CredentialSafeSession
from resdk.utils import url_origin


class _Request:
    """Minimal stand-in for a prepared request."""

    def __init__(self):
        self.headers = {}


def _jwt(**claims):
    """Return an unsigned token with the given claims."""

    def part(data):
        encoded = base64.urlsafe_b64encode(json.dumps(data).encode())
        return encoded.rstrip(b"=").decode()

    return f"{part({'alg': 'RS256'})}.{part(claims)}.signature"


EMAIL = "user@example.com"
TOKEN = _jwt(**{auth.EMAIL_CLAIM: EMAIL})


class TestResAuthBearer(unittest.TestCase):
    def test_bearer_sets_authorization_header(self):
        res_auth = ResAuth(url="http://localhost:8000", token="a.b.c")
        request = res_auth(_Request())
        self.assertEqual(request.headers["Authorization"], "Bearer a.b.c")

    def test_username_is_the_email_in_the_token(self):
        res_auth = ResAuth("http://localhost:8000", token=TOKEN)
        self.assertEqual(res_auth.username, EMAIL)

    def test_token_without_an_email_has_no_username(self):
        res_auth = ResAuth("http://localhost:8000", token="a.b.c")
        self.assertIsNone(res_auth.username)

    def test_token_is_keyword_only(self):
        # An old call ResAuth(username, password) must not send the password
        # as a bearer token.
        with self.assertRaises(TypeError):
            ResAuth("me@example.com", "hunter2")

    def test_login_clears_cookies_of_an_earlier_connection(self):
        resolwe = MagicMock()
        resolwe.url = "http://localhost:8000"
        resolwe.session.cookies = requests.utils.cookiejar_from_dict({"sessionid": "s"})
        with patch("resdk.resolwe.ResolweAPI"):
            Resolwe._login(resolwe, token="a.b.c")
        self.assertEqual(dict(resolwe.session.cookies), {})

    def test_empty_token_is_rejected(self):
        for token in ("", "  "):
            with self.assertRaises(ValueError):
                ResAuth(url="http://localhost:8000", token=token)

    def test_token_is_stripped(self):
        res_auth = ResAuth(url="http://localhost:8000", token=" a.b.c\n")
        self.assertEqual(res_auth(_Request()).headers["Authorization"], "Bearer a.b.c")

    def test_token_with_inner_whitespace_is_rejected(self):
        for token in ("a.b c", "a.b\nc", "a.b\x00c"):
            with self.assertRaises(ValueError):
                ResAuth(url="http://localhost:8000", token=token)

    def test_anonymous_sets_no_authorization_header(self):
        res_auth = ResAuth(url="http://localhost:8000")
        request = res_auth(_Request())
        self.assertNotIn("Authorization", request.headers)
        self.assertIsNone(res_auth.token)


class TestTokenFromEnv(unittest.TestCase):
    def test_returns_token_when_set(self):
        with patch.dict("os.environ", {auth.TOKEN_ENV_VAR: "tok"}, clear=False):
            self.assertEqual(auth.token_from_env(), "tok")

    def test_strips_whitespace(self):
        with patch.dict("os.environ", {auth.TOKEN_ENV_VAR: " tok\n"}, clear=False):
            self.assertEqual(auth.token_from_env(), "tok")

    def test_returns_none_when_blank(self):
        with patch.dict("os.environ", {auth.TOKEN_ENV_VAR: " \n"}, clear=False):
            self.assertIsNone(auth.token_from_env())

    def test_returns_none_when_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(auth.token_from_env())


ISSUER = "https://example.auth0.com/"
SETTINGS = auth.Auth0Settings(
    issuer=ISSUER,
    client_id="cid",
    audience="https://api.example",
    token_endpoint="https://example.auth0.com/oauth/token",
    authorization_endpoint="https://example.auth0.com/authorize",
    device_authorization_endpoint="https://example.auth0.com/oauth/device/code",
)


def _document(body, status=200):
    """Return a response with the JSON ``body``; ``ValueError`` if ``body`` is one."""
    response = MagicMock(status_code=status)
    if isinstance(body, Exception):
        response.json.side_effect = body
    else:
        response.json.return_value = body
    return response


class TestDiscover(unittest.TestCase):
    SERVER = "https://app.example"
    METADATA = {
        "resource": "https://app.example",
        "authorization_servers": [ISSUER],
        "client_id": "cid",
        "audience": "https://api.example",
        "scopes_supported": ["expressions:api"],
    }
    CONFIGURATION = {
        "issuer": ISSUER,
        "token_endpoint": "https://example.auth0.com/oauth/token",
        "authorization_endpoint": "https://example.auth0.com/authorize",
        "device_authorization_endpoint": "https://example.auth0.com/oauth/device/code",
        "jwks_uri": "https://example.auth0.com/.well-known/jwks.json",
    }

    def _discover(self, metadata=None, configuration=None, server=SERVER):
        documents = {
            "https://app.example/.well-known/oauth-protected-resource": metadata
            or self.METADATA,
            "https://example.auth0.com/.well-known/openid-configuration": configuration
            or self.CONFIGURATION,
        }

        def get(url, **kwargs):
            self.assertEqual(kwargs.get("allow_redirects"), False)
            self.assertIn("timeout", kwargs)
            document = documents.get(url)
            return _document({}, status=404) if document is None else document

        with patch.object(auth.requests, "get", side_effect=get) as get_mock:
            for url, document in documents.items():
                if not isinstance(document, MagicMock):
                    documents[url] = _document(document)
            return auth.Auth0Settings.discover(server), get_mock

    def test_settings_come_from_the_server_and_its_issuer(self):
        settings, get = self._discover()
        self.assertEqual(settings, SETTINGS)
        self.assertEqual(
            [call.args[0] for call in get.call_args_list],
            [
                "https://app.example/.well-known/oauth-protected-resource",
                "https://example.auth0.com/.well-known/openid-configuration",
            ],
        )

    def test_server_path_and_default_port_are_ignored(self):
        for server in ("https://app.example/", "https://app.example:443/api/"):
            with self.subTest(server=server):
                settings, _ = self._discover(server=server)
                self.assertEqual(settings, SETTINGS)

    def test_server_on_another_port_names_it_in_the_resource(self):
        metadata = {**self.METADATA, "resource": "https://app.example:8443"}

        def get(url, **kwargs):
            if url == "https://app.example:8443/.well-known/oauth-protected-resource":
                return _document(metadata)
            return _document(self.CONFIGURATION)

        with patch.object(auth.requests, "get", side_effect=get):
            settings = auth.Auth0Settings.discover("https://app.example:8443")
        self.assertEqual(settings, SETTINGS)

    def test_server_must_use_https(self):
        for server in ("http://app.example", "app.example", "https://"):
            with self.subTest(server=server):
                with patch.object(auth.requests, "get") as get:
                    with self.assertRaisesRegex(ValueError, "HTTPS"):
                        auth.Auth0Settings.discover(server)
                get.assert_not_called()

    def test_metadata_for_another_resource_is_rejected(self):
        for resource in (None, "https://other.example", "https://app.example/"):
            with self.subTest(resource=resource):
                metadata = {**self.METADATA, "resource": resource}
                with self.assertRaisesRegex(RuntimeError, "is for"):
                    self._discover(metadata=metadata)

    def test_exactly_one_https_issuer_is_required(self):
        for issuers in (
            None,
            [],
            ISSUER,
            [ISSUER, "https://other.auth0.com/"],
            ["http://example.auth0.com/"],
            [""],
            [None],
        ):
            with self.subTest(issuers=issuers):
                metadata = {**self.METADATA, "authorization_servers": issuers}
                with self.assertRaisesRegex(RuntimeError, "exactly one HTTPS"):
                    self._discover(metadata=metadata)

    def test_client_and_audience_are_required(self):
        for field in ("client_id", "audience"):
            for value in (None, "", 7):
                with self.subTest(field=field, value=value):
                    metadata = {**self.METADATA, field: value}
                    with self.assertRaisesRegex(RuntimeError, f"has no {field}"):
                        self._discover(metadata=metadata)

    def test_issuer_must_match_its_configuration(self):
        for issuer in ("https://example.auth0.com", "https://other.auth0.com/", None):
            with self.subTest(issuer=issuer):
                configuration = {**self.CONFIGURATION, "issuer": issuer}
                with self.assertRaisesRegex(RuntimeError, "names the issuer"):
                    self._discover(configuration=configuration)

    def test_endpoints_must_be_on_the_issuers_origin(self):
        for field in (
            "token_endpoint",
            "authorization_endpoint",
            "device_authorization_endpoint",
        ):
            for endpoint in (
                None,
                "https://attacker.example/oauth/token",
                "http://example.auth0.com/oauth/token",
                "https://example.auth0.com:8443/oauth/token",
                "https://example.auth0.com:bad/oauth/token",
            ):
                with self.subTest(field=field, endpoint=endpoint):
                    configuration = {**self.CONFIGURATION, field: endpoint}
                    with self.assertRaisesRegex(RuntimeError, "on its origin"):
                        self._discover(configuration=configuration)

    def test_unreadable_documents_are_reported(self):
        cases = (
            (_document({}, status=404), "HTTP 404"),
            (_document({}, status=302), "HTTP 302"),
            (_document(ValueError("not JSON")), "not JSON"),
            (_document(["not", "an", "object"]), "not a JSON object"),
        )
        for response, message in cases:
            with self.subTest(message=message):
                with patch.object(auth.requests, "get", return_value=response):
                    with self.assertRaisesRegex(RuntimeError, message):
                        auth.Auth0Settings.discover(self.SERVER)

    def test_server_without_metadata_is_pointed_to_the_token(self):
        # A web front end may answer the missing path with its index page.
        for response in (_document(ValueError("not JSON")), _document({}, status=404)):
            with self.subTest(status=response.status_code):
                with patch.object(auth.requests, "get", return_value=response):
                    with self.assertRaisesRegex(
                        RuntimeError, "protected resource metadata.*RESDK_TOKEN"
                    ):
                        auth.Auth0Settings.discover(self.SERVER)

    def test_issuer_without_configuration_is_not_blamed_on_the_server(self):
        with self.assertRaises(RuntimeError) as raised:
            self._discover(configuration=_document(ValueError("not JSON")))
        self.assertIn("OpenID configuration", str(raised.exception))
        self.assertNotIn(auth.TOKEN_ENV_VAR, str(raised.exception))

    def test_unreachable_server_is_reported(self):
        with patch.object(
            auth.requests, "get", side_effect=requests.ConnectionError("refused")
        ):
            with self.assertRaisesRegex(RuntimeError, "Cannot read the protected"):
                auth.Auth0Settings.discover(self.SERVER)

    def test_all_scopes_and_offline_access_are_requested(self):
        scopes = SETTINGS.scope.split()
        for scope in (
            "openid",
            "email",
            "offline_access",
            "expressions:api",
            "supermodel:score",
        ):
            self.assertIn(scope, scopes)


def _token_response(status=200, **body):
    response = MagicMock(ok=status < 400, status_code=status, text=str(body))
    response.json.return_value = body
    return response


class TestGetAccessToken(unittest.TestCase):
    def test_returns_env_token_without_browser(self):
        # When RESDK_TOKEN is set, no interactive sign-in is attempted.
        with patch.dict("os.environ", {auth.TOKEN_ENV_VAR: "env-token"}, clear=True):
            with patch.object(auth, "_browser_sign_in") as login_mock:
                self.assertEqual(auth.get_access_token(), "env-token")
                login_mock.assert_not_called()

    def test_interactive_login_used_without_env_token(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(auth, "_browser_available", return_value=True),
        ):
            with patch.object(
                auth, "_browser_sign_in", return_value={"access_token": "signed-token"}
            ) as m:
                self.assertEqual(auth.get_access_token(SETTINGS), "signed-token")
                m.assert_called_once_with(SETTINGS)


class TestSignIn(unittest.TestCase):
    def test_returns_a_renewing_session_without_resolwe(self):
        body = {"access_token": "a1", "refresh_token": "r1", "expires_in": 600}
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(auth, "_browser_sign_in", return_value=body):
                session = auth.sign_in(SETTINGS, device=False)
        self.assertIsInstance(session, auth.Auth0Session)
        self.assertTrue(session.can_refresh)
        self.assertEqual(session.access_token, "a1")

    def test_env_token_gives_a_fixed_session(self):
        with patch.dict("os.environ", {auth.TOKEN_ENV_VAR: "env-token"}, clear=True):
            session = auth.sign_in()
        self.assertFalse(session.can_refresh)
        self.assertEqual(session.access_token, "env-token")

    def test_signing_in_without_settings_is_explained(self):
        for kwargs in ({}, {"username": "u", "password": "p"}):
            with self.subTest(kwargs=kwargs):
                with (
                    patch.dict("os.environ", {}, clear=True),
                    patch.object(auth.requests, "post") as post,
                ):
                    with self.assertRaisesRegex(ValueError, "Auth0Settings.discover"):
                        auth.sign_in(**kwargs)
                post.assert_not_called()


class TestTokenEmail(unittest.TestCase):
    def test_email_is_read_from_the_access_token(self):
        self.assertEqual(auth.Auth0Session(TOKEN).email, EMAIL)

    def test_token_without_the_claim_names_no_email(self):
        for claims in ({}, {"email": EMAIL}, {auth.EMAIL_CLAIM: ""}):
            with self.subTest(claims=claims):
                self.assertIsNone(auth.Auth0Session(_jwt(**claims)).email)

    def test_claim_that_is_not_text_names_no_email(self):
        for value in (None, 7, [EMAIL], {"address": EMAIL}):
            with self.subTest(value=value):
                token = _jwt(**{auth.EMAIL_CLAIM: value})
                self.assertIsNone(auth.Auth0Session(token).email)

    def test_token_that_is_not_a_jwt_names_no_email(self):
        not_json = base64.urlsafe_b64encode(b"not json").decode()
        a_list = base64.urlsafe_b64encode(b'["user@example.com"]').decode()
        for token in (
            "opaque",
            "a.b.c",
            "a.\u017e.c",
            f"a.{not_json}.c",
            f"a.{a_list}.c",
            f"{TOKEN}.more.parts",
        ):
            with self.subTest(token=token):
                self.assertIsNone(auth.Auth0Session(token).email)

    def test_email_is_the_one_of_the_renewed_token(self):
        session = auth.Auth0Session.from_token_response(
            {"access_token": TOKEN, "refresh_token": "r1", "expires_in": 0}, SETTINGS
        )
        renewed = _jwt(**{auth.EMAIL_CLAIM: "renewed@example.com"})
        response = _token_response(access_token=renewed, expires_in=600)
        with patch.object(auth.requests, "post", return_value=response):
            session.access_token
        self.assertEqual(session.email, "renewed@example.com")


class TestDeviceSignIn(unittest.TestCase):
    CODE = {
        "device_code": "dev",
        "user_code": "BDWP-HQPK",
        "verification_uri": "https://example.auth0.com/activate",
        "verification_uri_complete": "https://example.auth0.com/activate?user_code=BDWP-HQPK",
        "expires_in": 900,
        "interval": 5,
    }

    def _run(self, *answers):
        responses = [_token_response(**self.CODE), *answers]
        with (
            patch.object(auth.requests, "post", side_effect=responses) as post,
            patch.object(auth.time, "sleep") as sleep,
            patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            try:
                return auth._device_sign_in(SETTINGS), post, sleep, stderr.getvalue()
            except Exception as error:
                return error, post, sleep, stderr.getvalue()

    def test_polls_until_approved(self):
        body, post, sleep, printed = self._run(
            _token_response(403, error="authorization_pending"),
            _token_response(429, error="slow_down"),
            _token_response(access_token="a1", refresh_token="r1", expires_in=600),
        )
        self.assertEqual(body["access_token"], "a1")
        self.assertIn("BDWP-HQPK", printed)
        self.assertIn("activate?user_code=BDWP-HQPK", printed)
        start = post.call_args_list[0]
        self.assertEqual(start.args[0], "https://example.auth0.com/oauth/device/code")
        self.assertEqual(start.kwargs["data"]["audience"], SETTINGS.audience)
        poll = post.call_args_list[1].kwargs["data"]
        self.assertEqual(
            poll,
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": "dev",
                "client_id": "cid",
            },
        )
        # slow_down adds 5 seconds to the interval.
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [5.0, 5.0, 10.0])

    def test_network_error_while_polling_keeps_polling(self):
        body, post, sleep, printed = self._run(
            requests.ConnectionError("reset"),
            _token_response(access_token="a1", refresh_token="r1", expires_in=600),
        )
        self.assertEqual(body["access_token"], "a1")

    def test_denied_sign_in_stops(self):
        error, *_ = self._run(_token_response(403, error="access_denied"))
        self.assertIsInstance(error, RuntimeError)
        self.assertIn("denied", str(error))

    def test_expired_code_stops(self):
        error, *_ = self._run(_token_response(403, error="expired_token"))
        self.assertIsInstance(error, TimeoutError)

    def test_unexpected_error_stops(self):
        error, *_ = self._run(_token_response(400, error="invalid_request"))
        self.assertIsInstance(error, RuntimeError)
        self.assertIn("did not issue a token", str(error))


class TestPasswordSignIn(unittest.TestCase):
    def test_sends_the_password_grant_to_auth0(self):
        ok = _token_response(access_token="a1", refresh_token="r1", expires_in=600)
        with patch.object(auth.requests, "post", return_value=ok) as post:
            session = auth.sign_in(SETTINGS, username="u@example.com", password="pw")
        self.assertTrue(session.can_refresh)
        self.assertEqual(
            post.call_args.args[0], "https://example.auth0.com/oauth/token"
        )
        data = post.call_args.kwargs["data"]
        self.assertEqual(data["grant_type"], "password")
        self.assertEqual((data["username"], data["password"]), ("u@example.com", "pw"))
        self.assertEqual(data["audience"], SETTINGS.audience)
        self.assertIn("offline_access", data["scope"])

    def test_refusal_is_explained_without_the_password(self):
        refused = _token_response(
            403, error="invalid_grant", error_description="Wrong email or password."
        )
        with patch.object(auth.requests, "post", return_value=refused):
            with self.assertRaises(RuntimeError) as raised:
                auth.sign_in(SETTINGS, username="u@example.com", password="secret-pw")
        self.assertIn("Wrong email or password.", str(raised.exception))
        self.assertNotIn("secret-pw", str(raised.exception))

    def test_password_wins_over_the_environment_token(self):
        ok = _token_response(access_token="a1", refresh_token="r1", expires_in=600)
        with (
            patch.dict("os.environ", {auth.TOKEN_ENV_VAR: "env-token"}, clear=True),
            patch.object(auth.requests, "post", return_value=ok),
        ):
            session = auth.sign_in(SETTINGS, username="u", password="p")
        self.assertEqual(session.access_token, "a1")


class TestNoRedirectsFromAuth0(unittest.TestCase):
    """Requests that carry credentials never follow a redirect off Auth0."""

    REDIRECT = _token_response(307)

    def test_password_is_not_resent_to_a_redirect(self):
        with patch.object(auth.requests, "post", return_value=self.REDIRECT) as post:
            with self.assertRaisesRegex(RuntimeError, "redirect") as raised:
                auth.sign_in(SETTINGS, username="u@example.com", password="secret-pw")
        self.assertIs(post.call_args.kwargs["allow_redirects"], False)
        self.assertNotIn("secret-pw", str(raised.exception))

    def test_device_sign_in_stops_at_a_redirect(self):
        with patch.object(auth.requests, "post", return_value=self.REDIRECT) as post:
            with self.assertRaisesRegex(RuntimeError, "redirect"):
                auth._device_sign_in(SETTINGS)
        self.assertIs(post.call_args.kwargs["allow_redirects"], False)

    def test_device_polling_stops_at_a_redirect(self):
        code = _token_response(**TestDeviceSignIn.CODE)
        with (
            patch.object(
                auth.requests, "post", side_effect=[code, self.REDIRECT]
            ) as post,
            patch.object(auth.time, "sleep"),
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            with self.assertRaisesRegex(RuntimeError, "redirect"):
                auth._device_sign_in(SETTINGS)
        self.assertIs(post.call_args.kwargs["allow_redirects"], False)

    def test_refresh_token_is_not_resent_to_a_redirect(self):
        session = auth.Auth0Session.from_token_response(
            {"access_token": "a1", "refresh_token": "r1", "expires_in": 0}, SETTINGS
        )
        with patch.object(auth.requests, "post", return_value=self.REDIRECT) as post:
            with self.assertRaisesRegex(RuntimeError, "redirect"):
                session.access_token
        self.assertIs(post.call_args.kwargs["allow_redirects"], False)


class TestLoginWithPassword(unittest.TestCase):
    def _resolwe(self, accepted, url="https://app.example"):
        resolwe = MagicMock(url=url)
        resolwe.auth.username = None

        def login(token=None):
            # The user lookup succeeds only when the server accepts the token.
            if accepted:
                resolwe.auth.username = "u@example.com"
            return accepted

        resolwe._login.side_effect = login
        return resolwe

    def _login(self, resolwe, sign_in=None):
        sign_in = sign_in or MagicMock(return_value="session")
        with (
            patch.object(auth.Auth0Settings, "discover", return_value=SETTINGS),
            patch.object(auth, "sign_in", sign_in),
        ):
            Resolwe._login_with_password(resolwe, "u@example.com", "pw")
        return sign_in

    def test_uses_the_tenant_the_server_names(self):
        resolwe = self._resolwe(accepted=True)
        with (
            patch.object(
                auth.Auth0Settings, "discover", return_value=SETTINGS
            ) as discover,
            patch.object(auth, "sign_in", return_value="session") as sign_in,
        ):
            Resolwe._login_with_password(resolwe, "u@example.com", "pw")
        discover.assert_called_once_with("https://app.example")
        sign_in.assert_called_once_with(
            SETTINGS, username="u@example.com", password="pw"
        )
        resolwe._login.assert_called_once_with(token="session")

    def test_server_without_a_tenant_never_gets_the_password(self):
        for error in (ValueError("not HTTPS"), RuntimeError("HTTP 404")):
            with self.subTest(error=error):
                resolwe = self._resolwe(accepted=True)
                with patch.object(auth.Auth0Settings, "discover", side_effect=error):
                    with patch.object(auth, "sign_in") as sign_in:
                        with self.assertRaises(type(error)):
                            Resolwe._login_with_password(resolwe, "u@example.com", "pw")
                sign_in.assert_not_called()
                resolwe._login.assert_not_called()

    def test_token_the_server_rejects_is_an_error(self):
        resolwe = self._resolwe(accepted=False)
        with self.assertRaisesRegex(RuntimeError, "did not accept the token"):
            self._login(resolwe)
        # The rejected token is not kept: the connection is anonymous.
        self.assertEqual(
            [c.kwargs for c in resolwe._login.call_args_list],
            [{"token": "session"}, {}],
        )

    def test_empty_username_or_password_is_an_error(self):
        for username, password in (("u@example.com", ""), ("", "pw")):
            with self.subTest(username=username, password=password):
                resolwe = self._resolwe(accepted=True)
                with (
                    patch.dict("os.environ", {auth.TOKEN_ENV_VAR: "env-token"}),
                    patch.object(auth.Auth0Settings, "discover") as discover,
                    patch.object(auth, "sign_in") as sign_in,
                ):
                    with self.assertRaisesRegex(ValueError, "username and a password"):
                        Resolwe._login_with_password(resolwe, username, password)
                discover.assert_not_called()
                sign_in.assert_not_called()
                resolwe._login.assert_not_called()

    def test_empty_password_at_the_prompt_is_an_error(self):
        resolwe = MagicMock(url="https://app.example")
        resolwe._login_with_password = lambda u, p: Resolwe._login_with_password(
            resolwe, u, p
        )
        with (
            patch("resdk.resolwe.getpass.getpass", return_value=""),
            patch.object(auth, "sign_in") as sign_in,
        ):
            with self.assertRaises(ValueError):
                Resolwe.login(resolwe, "u@example.com")
        sign_in.assert_not_called()
        resolwe.login_with_auth0.assert_not_called()

    def test_auth0_refusal_is_an_error(self):
        resolwe = self._resolwe(accepted=True)
        with self.assertRaisesRegex(RuntimeError, "refused"):
            self._login(resolwe, sign_in=MagicMock(side_effect=RuntimeError("refused")))
        resolwe._login.assert_not_called()

    def test_login_without_a_username_signs_in_through_auth0(self):
        resolwe = MagicMock()
        Resolwe.login(resolwe)
        resolwe.login_with_auth0.assert_called_once_with()
        resolwe._login_with_password.assert_not_called()

    def test_login_with_a_username_asks_for_the_password(self):
        resolwe = MagicMock()
        with patch("resdk.resolwe.getpass.getpass", return_value="pw") as ask:
            Resolwe.login(resolwe, "u@example.com")
        ask.assert_called_once()
        resolwe._login_with_password.assert_called_once_with("u@example.com", "pw")
        resolwe.login_with_auth0.assert_not_called()


def _answer(status, body=None):
    """Return the server's answer to the question whether it accepts the token."""
    response = MagicMock(status_code=status)
    if body is None:
        response.json.side_effect = ValueError("not JSON")
    else:
        response.json.return_value = body
    return response


#: Answers of a server that does not accept the token: an invalid token, a
#: token it refuses, and a server that ignores tokens and sees nobody.
REJECTIONS = (_answer(401), _answer(403), _answer(200, []))
#: A server that cannot be reached, or does not answer the question.
NO_ANSWERS = (
    requests.ConnectionError("unreachable"),
    requests.Timeout("too slow"),
    _answer(502),
    _answer(503),
    _answer(404),
    _answer(200),
    _answer(200, {"detail": "maintenance"}),
)


def _connection(answer, url="https://app.example"):
    """Return a connection whose server gives ``answer`` about the token."""
    resolwe = MagicMock(url=url)
    resolwe._confirm_token = lambda: Resolwe._confirm_token(resolwe)
    resolwe._login = lambda **kwargs: Resolwe._login(resolwe, **kwargs)
    if isinstance(answer, Exception):
        resolwe.session.get.side_effect = answer
    else:
        resolwe.session.get.return_value = answer
    return resolwe


class TestTokenLogin(unittest.TestCase):
    def _login(self, answer, token=TOKEN):
        resolwe = _connection(answer)
        with patch("resdk.resolwe.ResolweAPI"):
            resolwe.accepted = resolwe._login(token=token)
        return resolwe

    def test_username_is_the_email_in_the_token(self):
        # The server knows the account under another spelling; the token wins.
        resolwe = self._login(_answer(200, [{"email": "User@Example.com"}]))
        self.assertEqual(resolwe.auth.username, EMAIL)
        self.assertIs(resolwe.accepted, True)
        resolwe.user.get.assert_not_called()

    def test_accepted_token_without_an_email_gets_the_servers(self):
        # A server may read the account from another claim than ReSDK does.
        resolwe = self._login(_answer(200, [{"email": EMAIL}]), token="a.b.c")
        self.assertEqual(resolwe.auth.username, EMAIL)
        self.assertIs(resolwe.accepted, True)

    def test_server_url_with_a_path_asks_the_api_of_the_host(self):
        resolwe = _connection(_answer(200, [{"email": EMAIL}]), "https://host/x/")
        with patch("resdk.resolwe.ResolweAPI") as api:
            resolwe._login(token=TOKEN)
        self.assertEqual(api.call_args.args[0], "https://host/api/")
        self.assertEqual(resolwe.session.get.call_args.args, ("https://host/api/user",))

    def test_expired_session_signs_nobody_in(self):
        session = auth.Auth0Session(TOKEN)
        error = RuntimeError("The Auth0 session has expired; sign in again.")
        resolwe = _connection(error)
        with patch("resdk.resolwe.ResolweAPI"):
            accepted = resolwe._login(token=session)
        self.assertIs(accepted, False)
        self.assertIsNone(resolwe.auth.username)
        resolwe.logger.warning.assert_called_once()

    def test_server_is_asked_once_with_the_token_and_a_timeout(self):
        resolwe = self._login(_answer(200, [{"email": EMAIL}]))
        resolwe.session.get.assert_called_once()
        call = resolwe.session.get.call_args
        self.assertEqual(call.args, ("https://app.example/api/user",))
        self.assertEqual(call.kwargs["params"], {"current_only": "1"})
        self.assertIs(call.kwargs["auth"], resolwe.auth)
        self.assertGreater(call.kwargs["timeout"], 0)

    def test_rejected_token_signs_nobody_in(self):
        for answer in REJECTIONS:
            with self.subTest(status=answer.status_code):
                resolwe = self._login(answer)
                self.assertIsNone(resolwe.auth.username)
                self.assertIs(resolwe.accepted, False)

    def test_token_is_kept_when_the_server_does_not_answer(self):
        for answer in NO_ANSWERS:
            with self.subTest(answer=answer):
                resolwe = self._login(answer)
                self.assertEqual(resolwe.auth.username, EMAIL)
                self.assertEqual(resolwe.auth.token, TOKEN)
                self.assertIsNone(resolwe.accepted)
                resolwe.logger.warning.assert_called_once()


class TestPasswordLoginAgainstTheServer(unittest.TestCase):
    """What the server's answer about the Auth0 token does to a password login."""

    def _login(self, answer, token=TOKEN):
        resolwe = _connection(answer)
        session = auth.Auth0Session(token)
        with (
            patch.object(auth.Auth0Settings, "discover", return_value=SETTINGS),
            patch.object(auth, "sign_in", return_value=session),
            patch("resdk.resolwe.ResolweAPI"),
        ):
            Resolwe._login_with_password(resolwe, EMAIL, "pw")
        return resolwe, session

    def test_accepted_token_is_used(self):
        resolwe, session = self._login(_answer(200, [{"email": EMAIL}]))
        self.assertIs(resolwe.auth.tokens, session)

    def test_rejected_token_is_an_error(self):
        for answer in REJECTIONS:
            with self.subTest(status=answer.status_code):
                with self.assertRaisesRegex(RuntimeError, "did not accept the token"):
                    self._login(answer)

    def test_unreachable_server_keeps_the_token(self):
        for answer in NO_ANSWERS:
            with self.subTest(answer=answer):
                resolwe, session = self._login(answer)
                self.assertIs(resolwe.auth.tokens, session)
                self.assertEqual(resolwe.auth.username, EMAIL)

    def test_token_without_an_email_is_used_like_any_other(self):
        for answer in (_answer(200, [{"email": EMAIL}]), _answer(503)):
            with self.subTest(status=answer.status_code):
                resolwe, session = self._login(answer, token="a.b.c")
                self.assertIs(resolwe.auth.tokens, session)


class TestChoosingTheSignIn(unittest.TestCase):
    BODY = {"access_token": "a1", "refresh_token": "r1", "expires_in": 600}

    def _sign_in(self, env, **kwargs):
        with (
            patch.dict("os.environ", env, clear=True),
            patch.object(auth, "_device_sign_in", return_value=self.BODY) as device,
            patch.object(auth, "_browser_sign_in", return_value=self.BODY) as browser,
            patch.object(auth.sys, "platform", "linux"),
            patch.object(auth.webbrowser, "get"),
        ):
            auth.sign_in(SETTINGS, **kwargs)
        return device.called, browser.called

    def test_device_flow_over_ssh(self):
        env = {"SSH_CONNECTION": "1 2 3 4", "DISPLAY": ":0"}
        self.assertEqual(self._sign_in(env), (True, False))

    def test_device_flow_on_linux_without_a_display(self):
        self.assertEqual(self._sign_in({}), (True, False))

    def test_browser_with_a_display(self):
        self.assertEqual(self._sign_in({"DISPLAY": ":0"}), (False, True))

    def test_explicit_choice_wins(self):
        self.assertEqual(self._sign_in({}, device=False), (False, True))
        self.assertEqual(self._sign_in({"DISPLAY": ":0"}, device=True), (True, False))


class TestAuth0Session(unittest.TestCase):
    def _session(self, expires_in=600):
        return auth.Auth0Session.from_token_response(
            {"access_token": "a1", "refresh_token": "r1", "expires_in": expires_in},
            SETTINGS,
        )

    def test_deep_copy_keeps_the_session(self):
        session = self._session()
        # A resource in a payload holds its connection, and with it the session.
        connection = ResAuth(url="https://example.org", token=session)
        self.assertIs(copy.deepcopy({"auth": connection})["auth"].tokens, session)

    def test_valid_token_is_not_refreshed(self):
        session = self._session()
        with patch.object(auth.requests, "post") as post:
            self.assertEqual(session.access_token, "a1")
        post.assert_not_called()

    def test_token_is_refreshed_before_it_expires(self):
        session = self._session(expires_in=auth.Auth0Session.REFRESH_MARGIN_SECONDS)
        renewed = _token_response(access_token="a2", refresh_token="r2", expires_in=600)
        with patch.object(auth.requests, "post", return_value=renewed) as post:
            self.assertEqual(session.access_token, "a2")
            self.assertEqual(session.access_token, "a2")
        post.assert_called_once()
        self.assertEqual(
            post.call_args.args[0], "https://example.auth0.com/oauth/token"
        )
        self.assertEqual(
            post.call_args.kwargs["data"],
            {"grant_type": "refresh_token", "client_id": "cid", "refresh_token": "r1"},
        )

    def test_rotated_refresh_token_is_kept(self):
        session = self._session(expires_in=0)
        responses = [
            _token_response(access_token="a2", refresh_token="r2", expires_in=0),
            _token_response(access_token="a3", refresh_token="r3", expires_in=600),
        ]
        with patch.object(auth.requests, "post", side_effect=responses) as post:
            self.assertEqual(session.access_token, "a2")
            self.assertEqual(session.access_token, "a3")
        self.assertEqual(post.call_args.kwargs["data"]["refresh_token"], "r2")

    def test_failed_refresh_asks_to_sign_in_again(self):
        session = self._session(expires_in=0)
        expired = _token_response(400, error="invalid_grant")
        with patch.object(auth.requests, "post", return_value=expired):
            with self.assertRaisesRegex(RuntimeError, "sign in again"):
                session.access_token

    def test_temporary_refresh_failure_keeps_the_refresh_token(self):
        session = self._session(expires_in=0)
        responses = [
            _token_response(503, error="temporarily_unavailable"),
            _token_response(access_token="a2", refresh_token="r2", expires_in=600),
        ]
        with patch.object(auth.requests, "post", side_effect=responses) as post:
            with self.assertRaises(RuntimeError):
                session.access_token
            self.assertTrue(session.can_refresh)
            self.assertEqual(session.access_token, "a2")
        self.assertEqual(post.call_count, 2)

    def test_temporary_refresh_failure_keeps_a_valid_token(self):
        session = self._session(expires_in=30)
        failure = _token_response(503, error="temporarily_unavailable")
        with patch.object(auth.requests, "post", return_value=failure) as post:
            with self.assertLogs("resdk.auth", level="WARNING") as logs:
                self.assertEqual(session.access_token, "a1")
        post.assert_called_once()
        self.assertTrue(session.can_refresh)
        self.assertIn("could not be renewed", logs.output[0])

    def test_connection_error_during_refresh_keeps_a_valid_token(self):
        session = self._session(expires_in=30)
        down = requests.ConnectionError("Auth0 is unreachable")
        with patch.object(auth.requests, "post", side_effect=down):
            with self.assertLogs("resdk.auth", level="WARNING"):
                self.assertEqual(session.access_token, "a1")
        self.assertTrue(session.can_refresh)

    def test_expired_session_that_cannot_renew_asks_to_sign_in(self):
        session = self._session(expires_in=0)
        dead = _token_response(400, error="invalid_grant")
        with patch.object(auth.requests, "post", return_value=dead) as post:
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, "sign in again"):
                    session.access_token
        # Auth0 is asked only once; afterwards the session knows it has ended.
        post.assert_called_once()

    def test_token_from_elsewhere_is_never_refreshed(self):
        session = auth.Auth0Session("given")
        self.assertFalse(session.can_refresh)
        with patch.object(auth.requests, "post") as post:
            self.assertEqual(session.access_token, "given")
            self.assertFalse(session.refresh_after_rejection("given"))
        post.assert_not_called()

    def test_parallel_rejections_share_one_refresh(self):
        session = self._session()
        renewed = _token_response(access_token="a2", refresh_token="r2", expires_in=600)
        barrier = threading.Barrier(5)
        results = []

        def rejected():
            barrier.wait(timeout=5)
            results.append(session.refresh_after_rejection("a1"))

        with patch.object(auth.requests, "post", return_value=renewed) as post:
            threads = [threading.Thread(target=rejected) for _ in range(5)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
        post.assert_called_once()
        self.assertEqual(results, [True] * 5)
        self.assertEqual(session.access_token, "a2")


class _FakeAdapter(requests.adapters.BaseAdapter):
    """Answer each request with the next status; record the tokens sent.

    A status may be ``(302, location)`` to redirect.
    """

    def __init__(self, statuses):
        super().__init__()
        self.statuses = list(statuses)
        self.tokens = []
        self.sent = []

    def send(self, request, **kwargs):
        self.tokens.append(request.headers.get("Authorization"))
        self.sent.append((request.url, request.headers.get("Authorization")))
        response = requests.Response()
        status = self.statuses.pop(0)
        if isinstance(status, tuple):
            status, location = status
            response.headers["Location"] = location
        response.status_code = status
        response.request = request
        response.raw = io.BytesIO(b"{}")
        response.url = request.url
        response.connection = self
        return response

    def close(self):
        pass


class TestRetryAfterRejection(unittest.TestCase):
    def _get(self, statuses, tokens):
        adapter = _FakeAdapter(statuses)
        session = requests.Session()
        session.mount("https://", adapter)
        res_auth = ResAuth(url="https://resolwe.example", token=tokens)
        return session.get("https://resolwe.example/api/x", auth=res_auth), adapter

    def _tokens(self):
        return auth.Auth0Session.from_token_response(
            {"access_token": "a1", "refresh_token": "r1", "expires_in": 600}, SETTINGS
        )

    def test_rejected_token_is_renewed_and_the_request_resent(self):
        renewed = _token_response(access_token="a2", refresh_token="r2", expires_in=600)
        with patch.object(auth.requests, "post", return_value=renewed):
            response, adapter = self._get([401, 200], self._tokens())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(adapter.tokens, ["Bearer a1", "Bearer a2"])

    def test_second_rejection_is_returned(self):
        renewed = _token_response(access_token="a2", refresh_token="r2", expires_in=600)
        with patch.object(auth.requests, "post", return_value=renewed) as post:
            response, adapter = self._get([401, 401], self._tokens())
        self.assertEqual(response.status_code, 401)
        self.assertEqual(len(adapter.tokens), 2)
        post.assert_called_once()

    def test_rejection_by_another_origin_is_not_retried_with_the_token(self):
        adapter = _FakeAdapter([(302, "https://storage.example/file?sig=1"), 401])
        session = _CredentialSafeSession()
        session.credential_origin = url_origin("https://resolwe.example")
        session.mount("https://", adapter)
        res_auth = ResAuth(url="https://resolwe.example", token=self._tokens())
        with patch.object(auth.requests, "post") as post:
            response = session.get("https://resolwe.example/data/1", auth=res_auth)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            adapter.sent,
            [
                ("https://resolwe.example/data/1", "Bearer a1"),
                ("https://storage.example/file?sig=1", None),
            ],
        )
        post.assert_not_called()

    def test_failed_refresh_returns_the_rejection(self):
        expired = _token_response(400, error="invalid_grant")
        tokens = self._tokens()
        with patch.object(auth.requests, "post", return_value=expired) as post:
            response, adapter = self._get([401], tokens)
            self.assertEqual(response.status_code, 401)
            # The dead refresh token is dropped, so Auth0 is not asked again.
            self.assertEqual(tokens.access_token, "a1")
            self.assertFalse(tokens.refresh_after_rejection("a1"))
        post.assert_called_once()

    def test_a_renewed_token_that_is_rejected_again_is_not_renewed_again(self):
        renewed = _token_response(access_token="a2", refresh_token="r2", expires_in=600)
        tokens = self._tokens()
        with patch.object(auth.requests, "post", return_value=renewed) as post:
            self._get([401, 401], tokens)
            response, adapter = self._get([401], tokens)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(adapter.tokens, ["Bearer a2"])
        post.assert_called_once()

    def test_token_without_refresh_is_not_retried(self):
        response, adapter = self._get([401], "given")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(adapter.tokens, ["Bearer given"])


class TestLoginWithAuth0(unittest.TestCase):
    def _message(self, accepted, username=EMAIL):
        resolwe = MagicMock()
        resolwe.auth.username = username
        resolwe._login.return_value = accepted
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(auth.Auth0Settings, "discover", return_value=SETTINGS),
            patch.object(auth, "sign_in", return_value="tok"),
            patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            Resolwe.login_with_auth0(resolwe)
        resolwe._login.assert_called_once_with(token="tok")
        return stderr.getvalue()

    def test_settings_are_discovered_from_the_server(self):
        resolwe = MagicMock(url="https://app.example")
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(
                auth.Auth0Settings, "discover", return_value=SETTINGS
            ) as discover,
            patch.object(auth, "sign_in", return_value="tok") as sign_in,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            Resolwe.login_with_auth0(resolwe, device=True)
        discover.assert_called_once_with("https://app.example")
        sign_in.assert_called_once_with(SETTINGS, device=True)

    def test_env_token_needs_no_discovery(self):
        resolwe = MagicMock(url="https://app.example")
        with (
            patch.dict("os.environ", {auth.TOKEN_ENV_VAR: "env-token"}, clear=True),
            patch.object(auth.Auth0Settings, "discover") as discover,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            Resolwe.login_with_auth0(resolwe)
        discover.assert_not_called()
        self.assertEqual(
            resolwe._login.call_args.kwargs["token"].access_token, "env-token"
        )

    def test_prints_signed_in_account(self):
        self.assertIn(f"Signed in to Resolwe as {EMAIL}.", self._message(True))

    def test_does_not_claim_sign_in_when_the_server_rejects_the_token(self):
        message = self._message(False, username=None)
        self.assertNotIn("Signed in", message)
        self.assertIn("the server did not accept it", message)

    def test_does_not_claim_sign_in_when_the_server_does_not_answer(self):
        message = self._message(None)
        self.assertNotIn("Signed in", message)
        self.assertIn(EMAIL, message)
        self.assertIn("the server did not confirm it", message)


class TestLogin(unittest.TestCase):
    def test_ignores_callback_with_wrong_state(self):
        """A forged callback does not abort the sign-in; the real one completes it."""
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        statuses = []
        threads = []

        def open_browser(authorize_url):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(authorize_url).query)
            callback = f"http://127.0.0.1:{port}/callback"

            def redirect():
                for state, code in (
                    ("forged", "bad"),
                    ("forgé", "bad"),
                    (query["state"][0], "good"),
                ):
                    response = requests.get(
                        callback, params={"code": code, "state": state}, timeout=5
                    )
                    statuses.append(response.status_code)

            threads.append(threading.Thread(target=redirect))
            threads[0].start()

        token_response = MagicMock(ok=True, status_code=200)
        token_response.json.return_value = {"access_token": "tok"}
        with (
            patch.object(auth, "CALLBACK_PORT", port),
            patch.object(auth.webbrowser, "open", open_browser),
            patch.object(auth.requests, "post", return_value=token_response) as post,
        ):
            body = auth._browser_sign_in(SETTINGS)
        threads[0].join(timeout=5)

        self.assertEqual(body["access_token"], "tok")
        self.assertEqual(statuses, [400, 400, 200])
        self.assertEqual(post.call_args.kwargs["data"]["code"], "good")
        self.assertIs(post.call_args.kwargs["allow_redirects"], False)

    def test_stalled_connection_does_not_block_the_redirect(self):
        """A client that keeps a connection open does not hold up the sign-in."""
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        done = threading.Event()
        threads = []

        def trickle():
            # Send a byte now and then, so a per-read timeout never fires, for
            # longer than the sign-in deadline.
            with socket.create_connection(("127.0.0.1", port)) as conn:
                conn.sendall(b"G")
                for _ in range(16):
                    if done.wait(0.5):
                        break
                    conn.sendall(b"E")

        def open_browser(authorize_url):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(authorize_url).query)

            def redirect():
                time.sleep(0.5)  # Let the trickling connection be accepted first.
                requests.get(
                    f"http://127.0.0.1:{port}/callback",
                    params={"code": "good", "state": query["state"][0]},
                    timeout=10,
                )

            threads.extend(
                [threading.Thread(target=trickle), threading.Thread(target=redirect)]
            )
            for thread in threads:
                thread.start()

        token_response = MagicMock(ok=True, status_code=200)
        token_response.json.return_value = {"access_token": "tok"}
        try:
            with (
                patch.object(auth, "CALLBACK_PORT", port),
                patch.object(auth, "LOGIN_TIMEOUT_SECONDS", 5),
                patch.object(auth.webbrowser, "open", open_browser),
                patch.object(auth.requests, "post", return_value=token_response),
            ):
                body = auth._browser_sign_in(SETTINGS)
                self.assertEqual(body["access_token"], "tok")
        finally:
            done.set()
            for thread in threads:
                thread.join(timeout=15)


if __name__ == "__main__":
    unittest.main()
