"""ReSDK utils."""

import hashlib
import pathlib
import re
from typing import Union
from urllib.parse import urlparse


def is_email(value):
    """Check if given value looks like an email address."""
    email_regex = r"[^@]+@[^@]+\.[^@]+"
    return re.match(email_regex, value)


def url_origin(url: str) -> tuple:
    """Return the (scheme, host, port) of a URL, with the default port filled in.

    The host is in its ASCII (IDNA) form, as ``requests`` sends it.
    """
    parsed = urlparse(url)
    port = parsed.port or {"http": 80, "https": 443}.get(parsed.scheme)
    host = parsed.hostname
    if host and not host.isascii():
        host = host.encode("idna").decode("ascii")
    return parsed.scheme, host, port


def is_credential_origin(url: str, origin: tuple) -> bool:
    """Return whether credentials for ``origin`` may be sent to ``url``.

    True for the same origin, and for an http-to-https upgrade of an origin on
    the default port (as ``requests`` allows for the ``Authorization`` header).
    """
    if origin is None:
        return False
    scheme, host, port = origin
    target = url_origin(url)
    return target == origin or (
        scheme == "http" and port == 80 and target == ("https", host, 443)
    )


def md5(
    path: Union[str, pathlib.Path],
    chunk_size: int = 10 * 1024**2,
) -> str:
    """Get the md5 checksum of a file."""
    hash = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hash.update(chunk)

    return hash.hexdigest()
