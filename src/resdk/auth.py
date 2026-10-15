""".. Ignore pydocstyle D400.

==============
Authentication
==============

Auth0 sign-in for bearer-token authentication.

Implements the OAuth 2.0 Authorization Code flow with PKCE: the user signs in
at Auth0 in a browser, Auth0 redirects back to a short-lived HTTP server on
``127.0.0.1``, and the authorization code is exchanged for an access token.
The token is kept in memory only (never written to disk) and is sent to the
Resolwe server as ``Authorization: Bearer <token>`` by
:class:`resdk.resolwe.ResAuth`.

A token obtained elsewhere can be put in the ``RESDK_TOKEN`` environment
variable; ReSDK then signs nobody in.

.. autoclass:: resdk.auth.Auth0Settings
   :members:

.. autofunction:: resdk.auth.get_access_token

.. autofunction:: resdk.auth.token_from_env

"""

import base64
import hashlib
import http.server
import os
import secrets
import sys
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from typing import Optional

import requests

#: Environment variable holding a pre-obtained access token.
TOKEN_ENV_VAR = "RESDK_TOKEN"
#: Environment variable selecting the Auth0 tenant, a key of :data:`TENANTS`.
TENANT_ENV_VAR = "RESDK_AUTH0_TENANT"
DEFAULT_TENANT = "production"

#: The Auth0 tenants: their domain and the client ID of their Native
#: application. The client IDs are public; a Native application has no secret.
TENANTS = {
    # Used by app.genialis.com. Its application is created when the production
    # tenant is set up (REID-3054); until then, sign-in reports that it is
    # missing.
    "production": {"domain": "genialis.us.auth0.com", "client_id": None},
    # Used by qa.genialis.io.
    "test": {
        "domain": "genialis-test.eu.auth0.com",
        "client_id": "JbYl1IfXfr2MlAqHnr9MR4YBziiCytIh",
    },
}

DEFAULT_AUDIENCE = "https://api.genialis.com"
#: ``expressions:api`` is the scope the Resolwe server requires, and the
#: supermodel scopes let the same token score with gpm; Auth0 drops the scopes
#: the user does not hold. ``offline_access`` asks for a refresh token.
DEFAULT_SCOPE = (
    "openid profile email offline_access expressions:api "
    "supermodel:score supermodel:versions:read"
)
#: The port is fixed because the redirect URI must exactly match a callback
#: URL registered in the Auth0 application.
CALLBACK_PORT = 8484
REDIRECT_URI = f"http://127.0.0.1:{CALLBACK_PORT}/callback"
LOGIN_TIMEOUT_SECONDS = 300


class _CallbackServer(http.server.ThreadingHTTPServer):
    """Local server that receives the redirect from Auth0.

    Each connection is handled in its own thread, so a slow or stalled one
    cannot keep the server from accepting the real redirect or from checking
    the sign-in deadline. The threads are not waited for on close.
    """

    # On Windows, SO_REUSEADDR lets another program bind the same port and
    # receive the redirect, so it is set only on other systems.
    allow_reuse_address = sys.platform != "win32"
    block_on_close = False

    def handle_error(self, request, client_address) -> None:
        """Ignore connection errors, such as a client that disconnects early."""


@dataclass(frozen=True)
class Auth0Settings:
    """Auth0 tenant, client and API audience."""

    domain: str
    client_id: str
    audience: str = DEFAULT_AUDIENCE
    scope: str = DEFAULT_SCOPE

    @classmethod
    def for_tenant(cls, name: str = DEFAULT_TENANT) -> "Auth0Settings":
        """Build the settings of a tenant in :data:`TENANTS`.

        :raises ValueError: if the tenant is unknown or has no application yet.
        """
        if name not in TENANTS:
            raise ValueError(
                f"Unknown Auth0 tenant {name!r}; {TENANT_ENV_VAR} must be one of "
                f"{', '.join(sorted(TENANTS))}."
            )
        tenant = TENANTS[name]
        if not tenant["client_id"]:
            raise ValueError(
                f"Signing in to the {name!r} Auth0 tenant is not available yet: "
                "it has no application for ReSDK. Put an access token in "
                f"{TOKEN_ENV_VAR} instead."
            )
        return cls(domain=tenant["domain"], client_id=tenant["client_id"])

    @classmethod
    def from_env(cls) -> "Auth0Settings":
        """Build the settings of the tenant named in :data:`TENANT_ENV_VAR`.

        The production tenant is used when the variable is unset or blank.

        :raises ValueError: if the tenant is unknown or has no application yet.
        """
        name = os.environ.get(TENANT_ENV_VAR, "").strip() or DEFAULT_TENANT
        return cls.for_tenant(name)


def token_from_env() -> Optional[str]:
    """Return the access token from :data:`TOKEN_ENV_VAR`, or ``None`` if unset.

    Surrounding whitespace, such as a trailing newline from a file or a CI
    secret, is removed. A blank value counts as unset.
    """
    return os.environ.get(TOKEN_ENV_VAR, "").strip() or None


def get_access_token(settings: Optional[Auth0Settings] = None) -> str:
    """Return an Auth0 access token.

    The token from :data:`TOKEN_ENV_VAR` is used if set; otherwise the user is
    signed in through the browser.

    :param settings: Auth0 settings; read from the environment when omitted.
    """
    token = token_from_env()
    if token:
        return token
    if settings is None:
        settings = Auth0Settings.from_env()
    return _login(settings)


def _login(settings: Auth0Settings) -> str:
    """Sign the user in through the browser and return the access token."""
    # PKCE: the sign-in request carries only the SHA-256 challenge; the verifier
    # is revealed when the code is redeemed, so an intercepted code is useless
    # to anyone else.
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    # Auth0 echoes `state` in the redirect. A callback with any other state
    # did not come from this sign-in and is ignored.
    state = secrets.token_urlsafe(16)
    authorize_url = f"https://{settings.domain}/authorize?" + urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": settings.client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": settings.scope,
            "audience": settings.audience,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
    )

    # Query parameters of the redirect from Auth0, filled in by the handler.
    callback: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        """Receive the redirect from Auth0."""

        # Close a connection that stops sending, so its thread ends.
        timeout = 10

        def do_GET(self) -> None:
            """Record the callback query and tell the user to return."""
            url = urllib.parse.urlparse(self.path)
            query = dict(urllib.parse.parse_qsl(url.query))
            if url.path != "/callback" or not ("code" in query or "error" in query):
                self.send_error(404)
                return
            # Compare bytes: compare_digest rejects non-ASCII strings.
            received = query.get("state", "").encode()
            if not secrets.compare_digest(received, state.encode()):
                # Any web page can send a request here; keep waiting for the
                # real redirect instead of aborting the sign-in.
                self.send_error(400)
                return
            callback.update(query)
            if "code" in query:
                message = "Signed in to Resolwe. You can close this tab."
            else:
                message = "Sign-in failed; see the terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(message.encode())

        def log_message(self, *args: object) -> None:
            """Silence the default request logging."""

    try:
        server = _CallbackServer(("127.0.0.1", CALLBACK_PORT), Handler)
    except OSError as error:
        raise RuntimeError(
            f"Cannot listen on 127.0.0.1:{CALLBACK_PORT} for the Auth0 redirect "
            f"({error}). Stop the program using the port, or set {TOKEN_ENV_VAR} "
            "to an access token obtained elsewhere."
        ) from error

    with server:
        server.timeout = 1  # Return from handle_request() to check the deadline.
        print(
            "Opening the browser to sign in. If it does not open, visit:\n"
            f"{authorize_url}",
            file=sys.stderr,
        )
        webbrowser.open(authorize_url)
        deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
        while not callback:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"No sign-in within {LOGIN_TIMEOUT_SECONDS} s; try again."
                )
            server.handle_request()

    if "error" in callback:
        raise RuntimeError(
            f"Auth0 refused the sign-in: {callback['error']}: "
            f"{callback.get('error_description', '')}"
        )

    response = requests.post(
        f"https://{settings.domain}/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": settings.client_id,
            "code": callback["code"],
            "code_verifier": verifier,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"Auth0 did not issue a token: {response.text[:300]}")
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError(f"Auth0 response has no access_token: {response.text[:300]}")
    return token
