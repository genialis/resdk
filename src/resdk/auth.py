""".. Ignore pydocstyle D400.

==============
Authentication
==============

Auth0 sign-in for bearer-token authentication.

With a browser on this machine, it uses the OAuth 2.0 Authorization Code flow
with PKCE: the user signs in at Auth0 in a browser, Auth0 redirects back to a
short-lived HTTP server on ``127.0.0.1``, and the authorization code is
exchanged for an access token. Without one, for example over SSH or on a
remote Jupyter server, it uses the Device Authorization Flow (RFC 8628): it
prints an address and a short code, the user approves the sign-in on any
device, and Auth0 hands the token over.
The token is kept in memory only (never written to disk) and is sent to the
Resolwe server as ``Authorization: Bearer <token>`` by
:class:`resdk.resolwe.ResAuth`.

A token obtained elsewhere can be put in the ``RESDK_TOKEN`` environment
variable; ReSDK then signs nobody in.

Other packages, such as gpm, get a token that renews itself without
connecting to Resolwe::

    from resdk import auth

    session = auth.sign_in()
    headers = {"Authorization": f"Bearer {session.access_token}"}

.. autofunction:: resdk.auth.sign_in

.. autoclass:: resdk.auth.Auth0Session
   :members: access_token, can_refresh, refresh_after_rejection

.. autoclass:: resdk.auth.Auth0Settings
   :members:

.. autofunction:: resdk.auth.get_access_token

.. autofunction:: resdk.auth.token_from_env

"""

import base64
import hashlib
import http.server
import logging
import os
import secrets
import sys
import threading
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

logger = logging.getLogger(__name__)


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


class Auth0Session:
    """An Auth0 access token that renews itself before it expires.

    Holds the access token, the refresh token and the expiry in memory only.
    :attr:`access_token` returns a token that is valid for at least
    :attr:`REFRESH_MARGIN_SECONDS` more seconds, refreshing it at Auth0 when
    needed. Auth0 rotates the refresh token on every use, and the session keeps
    the new one. A token obtained elsewhere (``RESDK_TOKEN`` or
    :meth:`resdk.Resolwe.login_with_token`) has no refresh token and is used as
    it is until it expires.

    The session is safe to share between threads: one lock guards the refresh,
    so parallel requests share one refresh instead of each starting one.
    """

    #: Refresh this many seconds before the access token expires.
    REFRESH_MARGIN_SECONDS = 60

    def __init__(
        self,
        access_token: str,
        *,
        refresh_token: Optional[str] = None,
        expires_in: Optional[float] = None,
        settings: Optional[Auth0Settings] = None,
    ):
        """Hold a token, and the refresh token and settings to renew it."""
        self._lock = threading.Lock()
        self._access_token = access_token
        self._refresh_token = refresh_token
        # The token obtained by the last refresh after a rejection. If the
        # server rejects that one too, the problem is not an expired token, so
        # refreshing again would only spend refresh tokens.
        self._renewed_after_rejection: Optional[str] = None
        # Set when Auth0 says the refresh token is no longer valid.
        self._renewal_ended = False
        self._expires_at = self._expiry(expires_in)
        self.settings = settings

    @classmethod
    def from_token_response(cls, body: dict, settings: Auth0Settings) -> "Auth0Session":
        """Build a session from the JSON body of Auth0's token endpoint."""
        return cls(
            body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_in=body.get("expires_in"),
            settings=settings,
        )

    @property
    def can_refresh(self) -> bool:
        """Whether the session holds a refresh token and the settings to use it."""
        return bool(self._refresh_token and self.settings)

    @property
    def access_token(self) -> str:
        """Return a valid access token, refreshing it first if it is about to expire.

        A failed refresh is logged while the current token is still valid, so a
        temporary Auth0 error does not fail the request.

        :raises RuntimeError: if the token has expired and the refresh fails,
            for example because the refresh token has expired; sign in again
            then.
        """
        with self._lock:
            if self._expires_at is None:
                return self._access_token
            now = time.monotonic()
            if (
                self.can_refresh
                and now >= self._expires_at - self.REFRESH_MARGIN_SECONDS
            ):
                try:
                    self._refresh()
                except (RuntimeError, requests.RequestException) as error:
                    if time.monotonic() >= self._expires_at:
                        raise
                    logger.warning(
                        "The Auth0 access token could not be renewed; using the "
                        "current one, which is valid for another %.0f s. %s",
                        self._expires_at - time.monotonic(),
                        error,
                    )
            elif self._renewal_ended and now >= self._expires_at:
                raise RuntimeError("The Auth0 session has expired; sign in again.")
            return self._access_token

    def refresh_after_rejection(self, rejected: str) -> bool:
        """Refresh once after the server rejected ``rejected``.

        Refreshes only if ``rejected`` is still the current token; if another
        thread has refreshed meanwhile, its token is used instead.

        :return: whether a token other than ``rejected`` is now available.
        """
        with self._lock:
            if self._access_token != rejected:
                return True
            if not self.can_refresh or rejected == self._renewed_after_rejection:
                return False
            self._refresh()
            self._renewed_after_rejection = self._access_token
            return self._access_token != rejected

    def _refresh(self) -> None:
        """Trade the refresh token for a new pair; the caller holds the lock."""
        assert self.settings is not None and self._refresh_token is not None
        response = requests.post(
            f"https://{self.settings.domain}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self.settings.client_id,
                "refresh_token": self._refresh_token,
            },
            timeout=30,
        )
        if not response.ok:
            try:
                error = response.json().get("error")
            except ValueError:
                error = None
            if response.status_code in (400, 401, 403) and error in PERMANENT_ERRORS:
                # The refresh token is expired or revoked; asking again would
                # fail the same way. A rate limit or server error (429, 5xx) is
                # temporary, so the refresh token is kept for the next attempt.
                self._refresh_token = None
                self._renewal_ended = True
            raise RuntimeError(
                "The Auth0 session could not be renewed; sign in again. "
                f"Auth0 answered: {response.text[:300]}"
            )
        body = _token_body(response)
        self._access_token = body["access_token"]
        # Rotation: the old refresh token is now spent, so keep the new one.
        self._refresh_token = body.get("refresh_token", self._refresh_token)
        self._expires_at = self._expiry(body.get("expires_in"))

    @staticmethod
    def _expiry(expires_in: Optional[float]) -> Optional[float]:
        """Return the monotonic time at which a token of this lifetime expires."""
        if expires_in is None:
            return None
        return time.monotonic() + float(expires_in)


#: Errors from Auth0's token endpoint after which a refresh token is unusable.
PERMANENT_ERRORS = frozenset({"invalid_grant", "invalid_client", "unauthorized_client"})


def _token_body(response: requests.Response) -> dict:
    """Return the JSON body of a token response that holds an access token.

    :raises RuntimeError: if the request failed or no access token came back.
    """
    if not response.ok:
        raise RuntimeError(f"Auth0 did not issue a token: {response.text[:300]}")
    body = response.json()
    if not body.get("access_token"):
        raise RuntimeError(f"Auth0 response has no access_token: {response.text[:300]}")
    return body


def sign_in(
    settings: Optional[Auth0Settings] = None, *, device: Optional[bool] = None
) -> Auth0Session:
    """Sign in to Auth0 and return a session that renews its access token.

    The token in :data:`TOKEN_ENV_VAR` is used if set, without renewal;
    otherwise the user signs in. Nothing is written to disk, so every new
    process signs in again.

    :param settings: Auth0 settings; read from :data:`TENANT_ENV_VAR` when
        omitted.
    :param device: ``True`` to sign in with the Device Authorization Flow,
        ``False`` to use the browser on this machine. By default the device
        flow is used when this machine has no browser to open.
    """
    token = token_from_env()
    if token:
        return Auth0Session(token)
    if settings is None:
        settings = Auth0Settings.from_env()
    if device is None:
        device = not _browser_available()
    body = _device_sign_in(settings) if device else _browser_sign_in(settings)
    return Auth0Session.from_token_response(body, settings)


def _browser_available() -> bool:
    """Return whether a browser on this machine can receive Auth0's redirect.

    Over SSH, or on Linux without a display, a browser would open (if at all)
    on another machine, where the redirect to ``127.0.0.1`` cannot reach us.
    """
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return False
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        return False
    try:
        webbrowser.get()
    except webbrowser.Error:
        return False
    return True


def _device_sign_in(settings: Auth0Settings) -> dict:
    """Sign in with the Device Authorization Flow; return Auth0's token response.

    Prints an address and a code. The user opens the address on any device,
    checks the code and approves the sign-in; meanwhile this polls Auth0.

    :raises TimeoutError: if the code expires before the sign-in is approved.
    :raises RuntimeError: if the sign-in is denied or Auth0 refuses it.
    """
    response = requests.post(
        f"https://{settings.domain}/oauth/device/code",
        data={
            "client_id": settings.client_id,
            "scope": settings.scope,
            "audience": settings.audience,
        },
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"Auth0 did not start a sign-in: {response.text[:300]}")
    code = response.json()
    address = code.get("verification_uri_complete") or code["verification_uri"]
    print(
        f"To sign in to Resolwe, open {address} on any device and check that it "
        f"shows the code {code['user_code']}. Only approve codes that this "
        "program printed.",
        file=sys.stderr,
    )
    interval = float(code.get("interval", 5))
    deadline = time.monotonic() + float(code.get("expires_in", 900))
    while True:
        time.sleep(interval)
        if time.monotonic() > deadline:
            raise TimeoutError("The sign-in code expired before it was approved.")
        try:
            response = requests.post(
                f"https://{settings.domain}/oauth/token",
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": code["device_code"],
                    "client_id": settings.client_id,
                },
                timeout=30,
            )
        except requests.RequestException:
            # A dropped connection: keep polling until the code expires.
            continue
        if response.ok:
            return _token_body(response)
        try:
            error = response.json().get("error")
        except ValueError:
            error = None
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error == "expired_token":
            raise TimeoutError("The sign-in code expired before it was approved.")
        if error == "access_denied":
            raise RuntimeError("The sign-in was denied.")
        raise RuntimeError(f"Auth0 did not issue a token: {response.text[:300]}")


def get_access_token(settings: Optional[Auth0Settings] = None) -> str:
    """Return an Auth0 access token.

    The token from :data:`TOKEN_ENV_VAR` is used if set; otherwise the user
    signs in (see :func:`sign_in`). The token is not renewed; keep an
    :class:`Auth0Session` to have it renewed.

    :param settings: Auth0 settings; read from the environment when omitted.
    """
    return sign_in(settings).access_token


def _browser_sign_in(settings: Auth0Settings) -> dict:
    """Sign the user in through the browser and return Auth0's token response."""
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
    return _token_body(response)
