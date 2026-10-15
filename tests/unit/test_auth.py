"""Unit tests for bearer-token / Auth0 authentication."""

import io
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


class TestResAuthBearer(unittest.TestCase):
    def test_bearer_sets_authorization_header(self):
        res_auth = ResAuth(url="http://localhost:8000", token="a.b.c")
        request = res_auth(_Request())
        self.assertEqual(request.headers["Authorization"], "Bearer a.b.c")
        # No CSRF header or cookies are used with bearer auth.
        self.assertNotIn("X-CSRFToken", request.headers)
        self.assertEqual(res_auth.cookies, {})

    def test_token_wins_over_username_and_password(self):
        with patch.object(ResAuth, "automatic_login") as automatic_login:
            res_auth = ResAuth("user", "pass", "http://localhost:8000", token="a.b.c")
        automatic_login.assert_not_called()
        self.assertEqual(res_auth.cookies, {})

    def test_token_login_clears_session_cookies(self):
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


class TestAuth0Settings(unittest.TestCase):
    def test_test_tenant_is_selected_by_name(self):
        with patch.dict("os.environ", {"RESDK_AUTH0_TENANT": " test "}, clear=True):
            settings = auth.Auth0Settings.from_env()
        self.assertEqual(settings.domain, "genialis-test.eu.auth0.com")
        self.assertEqual(settings.client_id, auth.TENANTS["test"]["client_id"])
        self.assertEqual(settings.audience, "https://api.genialis.com")

    def test_production_is_the_default(self):
        tenants = {
            **auth.TENANTS,
            "production": {"domain": "p.example", "client_id": "p"},
        }
        with patch.object(auth, "TENANTS", tenants):
            for env in ({}, {"RESDK_AUTH0_TENANT": ""}):
                with patch.dict("os.environ", env, clear=True):
                    settings = auth.Auth0Settings.from_env()
                self.assertEqual(
                    (settings.domain, settings.client_id), ("p.example", "p")
                )

    def test_unknown_tenant_is_rejected(self):
        with patch.dict("os.environ", {"RESDK_AUTH0_TENANT": "staging"}, clear=True):
            with self.assertRaisesRegex(ValueError, "must be one of production, test"):
                auth.Auth0Settings.from_env()

    def test_tenant_without_an_application_is_explained(self):
        tenants = {
            **auth.TENANTS,
            "production": {"domain": "p.example", "client_id": None},
        }
        with patch.object(auth, "TENANTS", tenants):
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(ValueError) as raised:
                    auth.Auth0Settings.from_env()
        self.assertIn("not available yet", str(raised.exception))
        self.assertIn("RESDK_TOKEN", str(raised.exception))
        self.assertNotIn("RESDK_AUTH0_TENANT=test", str(raised.exception))

    def test_all_scopes_and_offline_access_are_requested(self):
        settings = auth.Auth0Settings.for_tenant("test")
        scopes = settings.scope.split()
        for scope in (
            "openid",
            "email",
            "offline_access",
            "expressions:api",
            "supermodel:score",
        ):
            self.assertIn(scope, scopes)

    def test_old_variables_are_ignored(self):
        env = {
            "RESDK_AUTH0_TENANT": "test",
            "RESDK_AUTH0_CLIENT_ID": "cid",
            "RESDK_AUTH0_DOMAIN": "example.auth0.com",
        }
        with patch.dict("os.environ", env, clear=True):
            settings = auth.Auth0Settings.from_env()
        self.assertEqual(settings.domain, "genialis-test.eu.auth0.com")


SETTINGS = auth.Auth0Settings(domain="example.auth0.com", client_id="cid")


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
        with patch.dict("os.environ", {}, clear=True):
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
                session = auth.sign_in(SETTINGS)
        self.assertIsInstance(session, auth.Auth0Session)
        self.assertTrue(session.can_refresh)
        self.assertEqual(session.access_token, "a1")

    def test_env_token_gives_a_fixed_session(self):
        with patch.dict("os.environ", {auth.TOKEN_ENV_VAR: "env-token"}, clear=True):
            session = auth.sign_in()
        self.assertFalse(session.can_refresh)
        self.assertEqual(session.access_token, "env-token")


class TestAuth0Session(unittest.TestCase):
    def _session(self, expires_in=600):
        return auth.Auth0Session.from_token_response(
            {"access_token": "a1", "refresh_token": "r1", "expires_in": expires_in},
            SETTINGS,
        )

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
    def test_prints_signed_in_account(self):
        resolwe = MagicMock()
        resolwe.auth.username = "user@example.com"
        with (
            patch.object(auth, "sign_in", return_value="tok"),
            patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            Resolwe.login_with_auth0(resolwe)
        resolwe._login.assert_called_once_with(token="tok")
        self.assertIn("Signed in to Resolwe as user@example.com.", stderr.getvalue())

    def test_does_not_claim_sign_in_when_account_is_unknown(self):
        resolwe = MagicMock()
        resolwe.auth.username = None
        with (
            patch.object(auth, "sign_in", return_value="tok"),
            patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            Resolwe.login_with_auth0(resolwe)
        self.assertNotIn("Signed in", stderr.getvalue())
        self.assertIn("did not identify the account", stderr.getvalue())


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

        token_response = MagicMock(ok=True)
        token_response.json.return_value = {"access_token": "tok"}
        with (
            patch.object(auth, "CALLBACK_PORT", port),
            patch.object(auth.webbrowser, "open", open_browser),
            patch.object(auth.requests, "post", return_value=token_response) as post,
        ):
            body = auth._browser_sign_in(
                auth.Auth0Settings(domain="example.auth0.com", client_id="cid")
            )
        threads[0].join(timeout=5)

        self.assertEqual(body["access_token"], "tok")
        self.assertEqual(statuses, [400, 400, 200])
        self.assertEqual(post.call_args.kwargs["data"]["code"], "good")

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

        token_response = MagicMock(ok=True)
        token_response.json.return_value = {"access_token": "tok"}
        try:
            with (
                patch.object(auth, "CALLBACK_PORT", port),
                patch.object(auth, "LOGIN_TIMEOUT_SECONDS", 5),
                patch.object(auth.webbrowser, "open", open_browser),
                patch.object(auth.requests, "post", return_value=token_response),
            ):
                body = auth._browser_sign_in(
                    auth.Auth0Settings(domain="example.auth0.com", client_id="cid")
                )
                self.assertEqual(body["access_token"], "tok")
        finally:
            done.set()
            for thread in threads:
                thread.join(timeout=15)


if __name__ == "__main__":
    unittest.main()
