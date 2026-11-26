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
device, and Auth0 hands the token over. Scripts and CI jobs with a username and
password sign in with the password grant, which needs no person.
The token is kept in memory only (never written to disk) and is sent to the
Resolwe server as ``Authorization: Bearer <token>`` by
:class:`resdk.resolwe.ResAuth`.

The Resolwe server names its Auth0 tenant, application and API: ReSDK reads
them from the server's protected resource metadata (RFC 9728) and the tenant's
OpenID Connect discovery document (see :meth:`Auth0Settings.discover`).

A token obtained elsewhere can be put in the ``RESDK_TOKEN`` environment
variable; ReSDK then signs nobody in.

Other packages, such as gpm, get a token that renews itself without
connecting to Resolwe::

    from resdk import auth

    settings = auth.Auth0Settings.discover("https://app.genialis.com")
    session = auth.sign_in(settings)
    headers = {"Authorization": f"Bearer {session.access_token}"}

.. autofunction:: resdk.auth.sign_in

.. autoclass:: resdk.auth.Auth0Session
   :members: access_token, email, can_refresh, refresh_after_rejection

.. autoclass:: resdk.auth.Auth0Settings
   :members:

.. autofunction:: resdk.auth.get_access_token

.. autofunction:: resdk.auth.token_from_env

"""

import base64
import hashlib
import http.server
import json
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

from .utils import url_origin

#: Environment variable holding a pre-obtained access token.
TOKEN_ENV_VAR = "RESDK_TOKEN"

#: Path of the protected resource metadata (RFC 9728) on the Resolwe server.
RESOURCE_METADATA_PATH = "/.well-known/oauth-protected-resource"
#: Path of the OpenID Connect discovery document, relative to the issuer.
OPENID_CONFIGURATION_PATH = "/.well-known/openid-configuration"
#: Seconds to wait for a discovery document.
DISCOVERY_TIMEOUT = 30

#: ``expressions:api`` is the scope the Resolwe server requires, and the
#: supermodel scopes let the same token score with gpm; Auth0 drops the scopes
#: the user does not hold. ``offline_access`` asks for a refresh token.
DEFAULT_SCOPE = (
    "openid profile email offline_access expressions:api "
    "supermodel:score supermodel:versions:read"
)
#: Claim of the access token that holds the user's email. The Resolwe server
#: identifies the user by it.
EMAIL_CLAIM = "https://genialis.com/email"

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
    """Auth0 tenant (the issuer and its endpoints), client and API audience."""

    issuer: str
    #: Client ID of the tenant's Native application for ReSDK. It is public; a
    #: Native application has no secret.
    client_id: str
    #: Identifier of the API the tokens are for.
    audience: str
    token_endpoint: str
    authorization_endpoint: str
    device_authorization_endpoint: str
    scope: str = DEFAULT_SCOPE

    @classmethod
    def discover(cls, server_url: str) -> "Auth0Settings":
        """Return the Auth0 settings that the Resolwe server at ``server_url`` names.

        The server's protected resource metadata (RFC 9728) names its
        authorization server (the Auth0 issuer), the client ID and the
        audience. The issuer's OpenID Connect discovery document gives the
        endpoints. The issuer must match on both sides and the endpoints must
        be on the issuer's origin, so credentials go only to the tenant that
        the server names.

        :raises ValueError: if ``server_url`` is not HTTPS.
        :raises RuntimeError: if a document cannot be read or fails a check.
        """
        scheme, host, port = url_origin(server_url)
        if scheme != "https" or not host:
            raise ValueError(
                f"Signing in through Auth0 needs an HTTPS server URL, not {server_url}."
            )
        resource = f"https://{host}" if port == 443 else f"https://{host}:{port}"
        metadata = _discovery_document(
            resource + RESOURCE_METADATA_PATH,
            "protected resource metadata",
            # A web front end may answer the missing path with its index page.
            absent=(
                "The server may not support Auth0 sign-in yet; set "
                f"{TOKEN_ENV_VAR} instead."
            ),
        )
        if metadata.get("resource") != resource:
            raise RuntimeError(
                f"The protected resource metadata of {resource} is for "
                f"{metadata.get('resource')!r}."
            )
        issuers = metadata.get("authorization_servers")
        if (
            not isinstance(issuers, list)
            or len(issuers) != 1
            or not _is_https(issuers[0])
        ):
            raise RuntimeError(
                f"The protected resource metadata of {resource} must name exactly "
                f"one HTTPS authorization server, not {issuers!r}."
            )
        issuer = issuers[0]
        for field in ("client_id", "audience"):
            if not isinstance(metadata.get(field), str) or not metadata[field]:
                raise RuntimeError(
                    f"The protected resource metadata of {resource} has no {field}."
                )

        configuration = _discovery_document(
            issuer.rstrip("/") + OPENID_CONFIGURATION_PATH, "OpenID configuration"
        )
        if configuration.get("issuer") != issuer:
            raise RuntimeError(
                f"The OpenID configuration of {issuer} names the issuer "
                f"{configuration.get('issuer')!r}."
            )
        endpoints = {}
        for field in (
            "token_endpoint",
            "authorization_endpoint",
            "device_authorization_endpoint",
        ):
            endpoint = configuration.get(field)
            if not _is_https(endpoint) or url_origin(endpoint) != url_origin(issuer):
                raise RuntimeError(
                    f"The {field} of {issuer} must be on its origin, not {endpoint!r}."
                )
            endpoints[field] = endpoint
        return cls(
            issuer=issuer,
            client_id=metadata["client_id"],
            audience=metadata["audience"],
            **endpoints,
        )


def _is_https(url: object) -> bool:
    """Return whether ``url`` is an HTTPS URL with a host."""
    if not isinstance(url, str):
        return False
    try:
        scheme, host, _ = url_origin(url)
    except ValueError:
        # An invalid port.
        return False
    return scheme == "https" and bool(host)


def _discovery_document(url: str, name: str, absent: str = "") -> dict:
    """Return the JSON object at ``url``, a discovery document called ``name``.

    Redirects are not followed: the document must come from the URL itself.

    :param absent: Sentence appended to the error when the server answers
        without the document: with a status other than 200, or not with JSON.
    :raises RuntimeError: if the document cannot be read or is not an object.
    """
    try:
        response = requests.get(url, timeout=DISCOVERY_TIMEOUT, allow_redirects=False)
    except requests.RequestException as error:
        raise RuntimeError(f"Cannot read the {name} at {url}: {error}") from error
    suffix = f" {absent}" if absent else ""
    if response.status_code != 200:
        raise RuntimeError(
            f"Cannot read the {name} at {url}: HTTP {response.status_code}.{suffix}"
        )
    try:
        document = response.json()
    except ValueError as error:
        raise RuntimeError(f"The {name} at {url} is not JSON.{suffix}") from error
    if not isinstance(document, dict):
        raise RuntimeError(f"The {name} at {url} is not a JSON object.")
    return document


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

    def __deepcopy__(self, memo: dict) -> "Auth0Session":
        """Return this session: a copy would sign in on its own.

        Resources deep-copy their payload, which can hold a resource and
        through it the connection and this session. Auth0 rotates the refresh
        token on every use, so two copies would invalidate each other's.
        """
        return self

    @property
    def can_refresh(self) -> bool:
        """Whether the session holds a refresh token and the settings to use it."""
        return bool(self._refresh_token and self.settings)

    @property
    def email(self) -> Optional[str]:
        """Return the email the access token names, or ``None`` if it names none.

        The email is read from the token without checking its signature and
        without contacting Auth0 or Resolwe. It tells which account the token
        is for and proves nothing: the Resolwe server verifies the token on
        every request.
        """
        email = _claims(self._access_token).get(EMAIL_CLAIM)
        return email if isinstance(email, str) and email else None

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
        response = _post_to_auth0(
            self.settings.token_endpoint,
            {
                "grant_type": "refresh_token",
                "client_id": self.settings.client_id,
                "refresh_token": self._refresh_token,
            },
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


def _claims(token: str) -> dict:
    """Return the claims of a JWT, unverified, or ``{}`` if ``token`` is not one."""
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    try:
        # The payload is base64url without padding.
        claims = json.loads(
            base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        )
    except ValueError:
        return {}
    return claims if isinstance(claims, dict) else {}


def _post_to_auth0(url: str, data: dict) -> requests.Response:
    """POST the form ``data`` to the Auth0 endpoint ``url``; return the response.

    Redirects are not followed: on a 307 or 308, requests would resend the
    form, with its password, code or refresh token, to whatever host the
    redirect names, past the origin check of :meth:`Auth0Settings.discover`.

    :raises RuntimeError: if Auth0 answers with a redirect.
    """
    response = requests.post(url, data=data, timeout=30, allow_redirects=False)
    if 300 <= response.status_code < 400:
        raise RuntimeError(
            f"Auth0 answered {url} with a redirect (HTTP {response.status_code}); "
            "ReSDK does not follow redirects of sign-in requests."
        )
    return response


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
    settings: Optional[Auth0Settings] = None,
    *,
    device: Optional[bool] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Auth0Session:
    """Sign in to Auth0 and return a session that renews its access token.

    With a username and password, Auth0 checks them directly (the password
    grant); this needs no person, so scripts and CI jobs can sign in. It works
    for accounts with an Auth0 password and without MFA. Otherwise the token
    in :data:`TOKEN_ENV_VAR` is used if set, without renewal, or the user
    signs in. Nothing is written to disk, so every new process signs in again.

    :param settings: Auth0 settings, usually from :meth:`Auth0Settings.discover`;
        needed unless the token comes from :data:`TOKEN_ENV_VAR`
    :param device: ``True`` to sign in with the Device Authorization Flow,
        ``False`` to use the browser on this machine. By default the device
        flow is used when this machine has no browser to open.
    :param username: the user's email, for the password grant
    :param password: the user's password, for the password grant
    :raises ValueError: if ``settings`` are needed but not given.
    """
    if username and password:
        settings = _required(settings)
        body = _password_sign_in(settings, username, password)
        return Auth0Session.from_token_response(body, settings)
    token = token_from_env()
    if token:
        return Auth0Session(token)
    settings = _required(settings)
    if device is None:
        device = not _browser_available()
    body = _device_sign_in(settings) if device else _browser_sign_in(settings)
    return Auth0Session.from_token_response(body, settings)


def _required(settings: Optional[Auth0Settings]) -> Auth0Settings:
    """Return ``settings``, which signing in needs.

    :raises ValueError: if ``settings`` is ``None``.
    """
    if settings is None:
        raise ValueError(
            "Signing in needs the Auth0 settings; get them from the Resolwe "
            "server with Auth0Settings.discover(server_url), or set "
            f"{TOKEN_ENV_VAR}."
        )
    return settings


def _password_sign_in(settings: Auth0Settings, username: str, password: str) -> dict:
    """Sign in with a username and password; return Auth0's token response.

    The password goes only to Auth0. Auth0's brute-force protection applies.

    :raises RuntimeError: if Auth0 refuses the credentials or the grant.
    """
    response = _post_to_auth0(
        settings.token_endpoint,
        {
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": settings.client_id,
            "audience": settings.audience,
            "scope": settings.scope,
        },
    )
    if not response.ok:
        try:
            error = response.json()
        except ValueError:
            error = {}
        reason = (
            error.get("error_description") or error.get("error") or response.status_code
        )
        raise RuntimeError(f"Auth0 refused the username and password: {reason}")
    return _token_body(response)


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
    response = _post_to_auth0(
        settings.device_authorization_endpoint,
        {
            "client_id": settings.client_id,
            "scope": settings.scope,
            "audience": settings.audience,
        },
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
            response = _post_to_auth0(
                settings.token_endpoint,
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": code["device_code"],
                    "client_id": settings.client_id,
                },
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

    :param settings: Auth0 settings, usually from :meth:`Auth0Settings.discover`;
        needed unless the token comes from :data:`TOKEN_ENV_VAR`
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
    authorize_url = (
        settings.authorization_endpoint
        + "?"
        + urllib.parse.urlencode(
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

    response = _post_to_auth0(
        settings.token_endpoint,
        {
            "grant_type": "authorization_code",
            "client_id": settings.client_id,
            "code": callback["code"],
            "code_verifier": verifier,
            "redirect_uri": REDIRECT_URI,
        },
    )
    return _token_body(response)
