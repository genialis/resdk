"""Functional tests for Auth0 bearer-token authentication.

They sign in through Auth0 and check that the Resolwe server gives no identity
to a request without credentials, answers 401 with the bearer challenge to a
tampered token and to an ID token, and answers 403 to a valid access token
without the ``expressions:api`` scope. The other functional tests sign in with
bearer tokens, which checks that the server accepts a valid token for the
right user.

The tests need a deploy with bearer authentication enabled that serves its
Auth0 discovery metadata (:meth:`resdk.auth.Auth0Settings.discover`)::

    SERVER_URL=https://<deploy host> \\
    USER_EMAIL=... USER_PASSWORD=... \\
    pytest tests/functional/auth/e2e_auth0.py

The user is the regular user of the other functional tests, whose server
login also checks the password at the tenant. It must have an Auth0 password,
no MFA, and the ``expressions:api`` scope. ``USER_EMAIL`` and
``USER_PASSWORD`` must be set explicitly, so the defaults of the other
functional tests never reach Auth0. The tests are skipped when the
credentials are not set or ``SERVER_URL`` is not HTTPS, and fail when the
server does not serve its discovery metadata. The other functional tests fail
in all those cases, so CI does not pass without them.
"""

import dataclasses
import functools
import os
import unittest
from urllib.parse import urljoin, urlparse

import requests

from resdk import auth
from resdk.resolwe import CURRENT_USER_POSTFIX

from ..base import URL, USER_EMAIL, USER_PASSWORD

#: The scope the server requires in every access token.
REQUIRED_SCOPE = "expressions:api"


#: Set only when the credentials are given explicitly, so the defaults of the
#: other functional tests never reach Auth0.
CREDENTIALS_SET = bool(os.environ.get("USER_EMAIL") and os.environ.get("USER_PASSWORD"))


@functools.cache
def _settings():
    """Return the Auth0 settings the server names, discovering them once."""
    return auth.Auth0Settings.discover(URL)


def _token_response(scope):
    """Sign in with the password grant for ``scope``; return Auth0's response."""
    settings = dataclasses.replace(_settings(), scope=scope)
    return auth._password_sign_in(settings, USER_EMAIL, USER_PASSWORD)


@functools.cache
def _default_tokens():
    """Return Auth0's response for the default scope, signing in once."""
    return _token_response(auth.DEFAULT_SCOPE)


def _current_user(token):
    """Request the current user with ``token`` as the bearer credential."""
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    with requests.Session() as session:
        # Without this, credentials from ~/.netrc replace the header.
        session.trust_env = False
        return session.get(
            urljoin(URL, CURRENT_USER_POSTFIX),
            params={"current_only": "1"},
            headers=headers,
            timeout=30,
        )


def _emails(response):
    """Return the lower-cased emails in a current-user response."""
    return [str(user.get("email", "")).lower() for user in response.json()]


class TestAuth0Bearer(unittest.TestCase):
    def setUp(self):
        if urlparse(URL).scheme != "https":
            self.skipTest(
                f"Set an HTTPS SERVER_URL of a deploy with bearer authentication, "
                f"not {URL}."
            )
        if not CREDENTIALS_SET:
            self.skipTest("Set USER_EMAIL and USER_PASSWORD.")

    def assert_invalid_token_response(self, response):
        """Check the answer to a token the server must not accept.

        A 403, or a 401 without the challenge, means the server took the
        request for something else, or a proxy dropped the header.
        """
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers.get("WWW-Authenticate"), 'Bearer realm="api"')

    def test_missing_credential_has_no_identity(self):
        response = _current_user(None)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(_emails(response), [])

    def test_tampered_token_is_rejected(self):
        header, payload, signature = _default_tokens()["access_token"].split(".")
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
        response = _current_user(_default_tokens()["id_token"])

        self.assert_invalid_token_response(response)

    def test_access_token_without_scope_is_forbidden(self):
        # The API audience is shared with other services, and their tokens must
        # not sign in to Resolwe. This token is genuine and for the right
        # audience; only the scope is missing, because it is not requested.
        token = _token_response("openid")["access_token"]
        granted = auth._claims(token).get("scope", "").split()
        # Auth0 must grant the requested scope and nothing that was not
        # requested; otherwise the tenant or its post-login Action is wrong.
        if not granted or REQUIRED_SCOPE in granted:
            self.fail(
                f"Expected an access token with scopes but without "
                f"{REQUIRED_SCOPE}; Auth0 granted {granted!r} for 'openid'."
            )

        response = _current_user(token)

        self.assertEqual(response.status_code, 403)
