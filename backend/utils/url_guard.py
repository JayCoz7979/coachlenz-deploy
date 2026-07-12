"""SSRF guard for user-submitted film URLs.

CoachLenz lets a user paste a film URL that the server then fetches with yt-dlp /
ffprobe / ffmpeg. Without validation that is a server-side request forgery hole: a
user could submit `http://169.254.169.254/...` (cloud metadata / IAM creds),
`http://localhost:PORT/...` (internal services), or `file:///etc/passwd` (local
read), and the fetched bytes land in the user's own R2 bucket for download.

`validate_public_http_url` enforces: http(s) scheme only (blocks file://, gopher://,
etc.) and a PUBLIC destination (blocks private, loopback, link-local, reserved,
multicast). It resolves every A/AAAA record and blocks if ANY is internal.

Residual: DNS rebinding between this check and the actual fetch is not fully closed
(would require pinning the resolved IP through yt-dlp). This is defense at the API
boundary plus a re-check in the worker; good enough to stop the practical attacks.
"""
import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # can't parse -> refuse
    if ip.version == 6 and ip.ipv4_mapped is not None:
        # ::ffff:169.254.169.254 style — judge on the embedded v4 address.
        return _is_blocked_ip(str(ip.ipv4_mapped))
    return bool(
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def validate_public_http_url(url: str) -> str:
    """Return the URL if it is a plain http(s) URL to a public host; else raise
    ValueError with a user-safe message."""
    if not url or not isinstance(url, str):
        raise ValueError("Missing film URL.")
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError("Only http and https film links are supported.")
    host = parsed.hostname
    if not host:
        raise ValueError("That film link has no host.")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ValueError("Could not resolve that film link's host.")
    for info in infos:
        ip = info[4][0]
        if _is_blocked_ip(ip):
            raise ValueError("That link points to a private or internal address, which isn't allowed.")
    return url
