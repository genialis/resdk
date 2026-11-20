"""Functional tests for Auth0 bearer-token authentication.

They sign in through Auth0 and check that the Resolwe server accepts a valid
access token for the right user, gives no identity to a request without
credentials, answers 401 with the bearer challenge to a tampered token and to
an ID token, and answers 403 to a valid access token without the
``expressions:api`` scope.

The tests need a deploy with bearer authentication enabled and a tenant in
``resdk.auth.TENANTS`` that serves it, for example::

    SERVER_URL=https://qa.genialis.io RESDK_AUTH0_TENANT=test \\
    USER_EMAIL=... USER_PASSWORD=... \\
    pytest tests/functional/auth/e2e_auth0.py

The user must have an Auth0 password, no MFA, and the ``expressions:api``
scope (through the ``Expressions API user`` role or a verified
``@genialis.com`` address). The tests are skipped when the selected tenant
does not serve ``SERVER_URL``, as on a local server. Set
``RESDK_E2E_REQUIRE_AUTH0=1`` to fail instead of skipping.
"""

import dataclasses
import os
import unittest
from urllib.parse import urljoin

import requests

from resdk import Resolwe, auth
from resdk.resolwe import CURRENT_USER_POSTFIX

from ..base import URL, USER_EMAIL, USER_PASSWORD

#: The scope the server requires in every access token.
REQUIRED_SCOPE = "expressions:api"
REQUIRE_AUTH0 = os.environ.get("RESDK_E2E_REQUIRE_AUTH0", "").lower() in ("1", "true")


def _settings_for_url():
    """Return the Auth0 settings of the selected tenant if it serves ``URL``."""
    try:
        settings = auth.Auth0Settings.from_env()
    except ValueError:
        return None
    return settings if settings.serves(URL) else None


SETTINGS = _settings_for_url()


def _skip_or_fail(test, message):
    """Skip the test, or fail it when ``RESDK_E2E_REQUIRE_AUTH0`` is set."""
    if REQUIRE_AUTH0:
        test.fail(message)
    test.skipTest(message)


def _token_response(scope):
    """Sign in with the password grant for ``scope``; return Auth0's response."""
    settings = dataclasses.replace(SETTINGS, scope=scope)
    return auth._password_sign_in(settings, USER_EMAIL, USER_PASSWORD)


def _current_user(token):
    """Request the current user with ``token`` as the bearer credential."""
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    return requests.get(
        urljoin(URL, CURRENT_USER_POSTFIX),
        params={"current_only": "1"},
        headers=headers,
        timeout=30,
    )


def _emails(response):
    """Return the lower-cased emails in a current-user response."""
    return [str(user.get("email", "")).lower() for user in response.json()]


class TestAuth0Bearer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tokens = None
        if SETTINGS is not None:
            cls.tokens = _token_response(auth.DEFAULT_SCOPE)

    def setUp(self):
        if SETTINGS is None:
            _skip_or_fail(
                self,
                f"No Auth0 tenant serves {URL}; set SERVER_URL and "
                f"{auth.TENANT_ENV_VAR} to a deploy with bearer authentication.",
            )

    def assert_invalid_token_response(self, response):
        """Check the answer to a token the server must not accept.

        A 403, or a 401 without the challenge, means the server took the
        request for something else, or a proxy dropped the header.
        """
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers.get("WWW-Authenticate"), 'Bearer realm="api"')

    def test_password_sign_in_uses_bearer_token(self):
        res = Resolwe(USER_EMAIL, USER_PASSWORD, URL)

        # Without a token, ReSDK fell back to the server's password login: Auth0
        # refused the password or the server did not accept the token.
        self.assertIsNotNone(res.auth.tokens)
        self.assertEqual(res.auth.cookies, {})
        # The identity, not only a 200: the server answers an anonymous request
        # with 200 and no user.
        user = res.user.get(current_only=True)
        self.assertEqual(user.email.lower(), USER_EMAIL.lower())

    def test_missing_credential_has_no_identity(self):
        response = _current_user(None)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(_emails(response), [])

    def test_tampered_token_is_rejected(self):
        header, payload, signature = self.tokens["access_token"].split(".")
        # Change a character in the middle of the signature. The last character
        # holds only the final bits of the signature, so changing it can decode
        # to the same bytes and leave the token valid.
        middle = len(signature) // 2
        replacement = "A" if signature[middle] != "A" else "B"
        signature = signature[:middle] + replacement + signature[middle + 1 :]

        response = _current_user(".".join([header, payload, signature]))

        self.assert_invalid_token_response(response)

    def test_id_token_is_rejected(self):
        # A genuine token from the tenant, but issued for the client, not for
        # the API: invalid (401), not a valid token without the scope (403).
        response = _current_user(self.tokens["id_token"])

        self.assert_invalid_token_response(response)

    def test_access_token_without_scope_is_forbidden(self):
        # The API audience is shared with other services, and their tokens must
        # not sign in to Resolwe. This token is genuine and for the right
        # audience; only the scope is missing, because it is not requested.
        token = _token_response("openid")["access_token"]
        granted = auth._claims(token).get("scope", "").split()
        if not granted or REQUIRED_SCOPE in granted:
            _skip_or_fail(
                self,
                f"Expected an access token with scopes but without "
                f"{REQUIRED_SCOPE}; Auth0 granted {granted!r} for 'openid'.",
            )

        response = _current_user(token)

        self.assertEqual(response.status_code, 403)
