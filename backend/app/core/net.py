"""Outbound HTTP for agents and tools: SSRF-guarded, size- and time-limited.

Everything fetched from the internet is untrusted data. This module only decides *whether* a
URL may be fetched; callers must still treat the body as untrusted (see ``app.agents.runtime``).
"""

import ipaddress
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

USER_AGENT = "MATT-Agent/0.1 (+https://github.com/sharathhy/MattAgent)"
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 3
ALLOWED_PORTS = {None, 80, 443}

Resolver = Callable[[str], list[str]]


class BlockedURL(ValueError):
    pass


def system_resolver(host: str) -> list[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(host, None)]


def check_url(url: str, resolve: Resolver = system_resolver) -> None:
    """Reject non-HTTP schemes, odd ports, credentials in URLs, and private/internal hosts."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise BlockedURL(f"Scheme not allowed: {parts.scheme or 'none'}")
    if parts.username or parts.password:
        raise BlockedURL("Credentials in URLs are not allowed")
    if parts.port not in ALLOWED_PORTS:
        raise BlockedURL(f"Port not allowed: {parts.port}")
    host = parts.hostname
    if not host:
        raise BlockedURL("URL has no host")
    if host.lower() in ("localhost",) or host.lower().endswith((".local", ".internal")):
        raise BlockedURL("Internal hostnames are not allowed")
    try:
        addresses = resolve(host)
    except OSError as exc:
        raise BlockedURL(f"Cannot resolve {host}") from exc
    for addr in addresses:
        ip = ipaddress.ip_address(addr)
        if not ip.is_global or ip.is_multicast:
            raise BlockedURL(f"{host} resolves to a non-public address")


def ipv4_transport() -> httpx.HTTPTransport:
    """Connect over IPv4. Hosts like Render have no IPv6 route, and when a site's DNS lists an
    IPv6 address first the connection fails with "[Errno 101] Network is unreachable"."""
    return httpx.HTTPTransport(local_address="0.0.0.0", retries=1)  # noqa: S104 (outbound source address, not a listener)


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    headers: dict[str, str]
    text: str
    elapsed_ms: int
    bytes: int
    truncated: bool


def safe_fetch(
    url: str,
    *,
    client: httpx.Client | None = None,
    resolve: Resolver = system_resolver,
    timeout: float = 10.0,
    method: str = "GET",
) -> FetchResult:
    """Fetch a public URL, re-checking every redirect hop."""
    own = client is None
    client = client or httpx.Client(
        timeout=timeout, follow_redirects=False, transport=ipv4_transport()
    )
    try:
        current = url
        start = time.perf_counter()
        for _ in range(MAX_REDIRECTS + 1):
            check_url(current, resolve)
            with client.stream(
                method, current, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"}
            ) as r:
                if r.is_redirect and "location" in r.headers:
                    current = urljoin(current, r.headers["location"])
                    continue
                chunks: list[bytes] = []
                size = 0
                truncated = False
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        truncated = True
                        break
                    chunks.append(chunk)
                body = b"".join(chunks)
                return FetchResult(
                    url=current,
                    status=r.status_code,
                    headers={k.lower(): v for k, v in r.headers.items()},
                    text=body.decode(r.encoding or "utf-8", errors="replace"),
                    elapsed_ms=int((time.perf_counter() - start) * 1000),
                    bytes=size,
                    truncated=truncated,
                )
        raise BlockedURL("Too many redirects")
    finally:
        if own:
            client.close()
