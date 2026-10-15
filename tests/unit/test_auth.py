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
from resdk.resolwe import ResAuth, Resolwe


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


class TestGetAccessToken(unittest.TestCase):
    def test_returns_env_token_without_browser(self):
        # When RESDK_TOKEN is set, no interactive sign-in is attempted.
        with patch.dict("os.environ", {auth.TOKEN_ENV_VAR: "env-token"}, clear=True):
            with patch.object(auth, "_login") as login_mock:
                self.assertEqual(auth.get_access_token(), "env-token")
                login_mock.assert_not_called()

    def test_interactive_login_used_without_env_token(self):
        settings = auth.Auth0Settings(domain="example.auth0.com", client_id="cid")
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(auth, "_login", return_value="signed-token") as m:
                self.assertEqual(auth.get_access_token(settings), "signed-token")
                m.assert_called_once_with(settings)


class TestLoginWithAuth0(unittest.TestCase):
    def test_prints_signed_in_account(self):
        resolwe = MagicMock()
        resolwe.auth.username = "user@example.com"
        with (
            patch.object(auth, "get_access_token", return_value="tok"),
            patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            Resolwe.login_with_auth0(resolwe)
        resolwe._login.assert_called_once_with(token="tok")
        self.assertIn("Signed in to Resolwe as user@example.com.", stderr.getvalue())

    def test_does_not_claim_sign_in_when_account_is_unknown(self):
        resolwe = MagicMock()
        resolwe.auth.username = None
        with (
            patch.object(auth, "get_access_token", return_value="tok"),
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
            token = auth._login(
                auth.Auth0Settings(domain="example.auth0.com", client_id="cid")
            )
        threads[0].join(timeout=5)

        self.assertEqual(token, "tok")
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
                self.assertEqual(
                    auth._login(
                        auth.Auth0Settings(domain="example.auth0.com", client_id="cid")
                    ),
                    "tok",
                )
        finally:
            done.set()
            for thread in threads:
                thread.join(timeout=15)


if __name__ == "__main__":
    unittest.main()
