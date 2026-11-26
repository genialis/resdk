"""Functional tests for ReSDK."""

import os
import unittest
from unittest.mock import patch

from resdk import Resolwe, auth

URL = os.environ.get("SERVER_URL", "http://localhost:8000")

# Get the regular user credentials from environment variables.
# Fallback to default values if the environment variables are not set.
USER_USERNAME = os.environ.get("USER_USERNAME", "user")
USER_EMAIL = os.environ.get("USER_EMAIL", "user@genialis.com")
USER_PASSWORD = os.environ.get("USER_PASSWORD", "user")

# Get the admin user credentials from environment variables.
# Fallback to default values if the environment variables are not set.
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@genialis.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

#: The Auth0 session of each user, by email. Each user signs in once per test
#: run and later tests reuse it: Auth0 throttles an account to 10 logins a
#: minute from one IP after 20, so signing in for every test hits that limit.
_SIGNED_IN: dict[str, auth.Auth0Session] = {}

FILES_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "files")
)


class BaseResdkFunctionalTest(unittest.TestCase):
    """Base class for functional tests in ReSDK.

    It generates 2 Resolwe classes for connection to server. One with
    admin's credentials (``self.res``) and one with normal user's
    credentials (``self.user_res``).

    """

    def setUp(self):
        """Sign in the admin and the regular user with Auth0 bearer tokens."""
        self.res = self.sign_in(ADMIN_EMAIL, ADMIN_PASSWORD)
        self.user_res = self.sign_in(USER_EMAIL, USER_PASSWORD)

    def sign_in(self, email: str, password: str) -> Resolwe:
        """Return a new connection signed in as ``email`` with a bearer token.

        The first call for a user signs in; later calls replay its result
        through the same code path, without contacting Auth0.
        """
        signed_in = _SIGNED_IN.get(email)
        # ReSDK discovers the Auth0 tenant from the server, as it does for
        # users, so the deploy's discovery metadata is under test too.
        if signed_in is None:
            res = Resolwe(email, password, URL)
        else:
            with patch.object(auth, "sign_in", return_value=signed_in):
                res = Resolwe(email, password, URL)
        # ReSDK falls back to the server's password login when discovery, Auth0
        # or the server refuses; the tests must run with a bearer token.
        if res.auth.tokens is None:
            self.fail(
                f"{email} did not sign in with a bearer token at {URL}; the "
                "server must be HTTPS and serve its Auth0 discovery metadata."
            )
        _SIGNED_IN[email] = res.auth.tokens
        return res

    def set_slug(self, resource, slug):
        """Set slug of resource."""
        resource.slug = slug
        resource.save()
