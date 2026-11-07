"""What stands in for an API token now that the service is local only.

There is no key to hand out: the service listens on loopback and nothing leaves the machine. What is
left to defend against is the browser. A web page you have open can send requests to
http://127.0.0.1:<port> (a form POST, or DNS rebinding that makes its own hostname resolve to this
machine), so two things are checked on every request:

* the `Host` must be one of this machine's own names (`allowed_hosts`). That defeats DNS rebinding,
  because a rebound page still sends its own hostname.
* a write (POST, PUT, PATCH, DELETE) that carries an `Origin`, or `Sec-Fetch-Site: cross-site`,
  must come from one of those names too, and from the port the request was sent to (the port in
  its `Host` header; the scheme's default when there is none). A form on another site cannot
  upload, cancel, re-enrich or delete, and nor can a page served by some other program on this
  machine, such as a dev server on localhost:5173.

curl and scripts send neither header, so they are unaffected.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("lens.api")

_WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def normalise_hosts(hosts: Iterable[str]) -> frozenset[str]:
    """Lower-case host names without brackets or ports: '[::1]' and '::1' are the same name."""
    names: set[str] = set()
    for host in hosts:
        name = (urlsplit("//" + host.strip()).hostname or host).strip("[]").lower()
        if name:
            names.add(name)
    return frozenset(names)


def _hostname(url: str) -> str | None:
    """The lower-cased host name of `url`, or None if there is none or it is malformed (an
    unclosed bracket such as `[::1` makes `urlsplit` raise)."""
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    return host.lower() if host else None


_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin_matches_host(origin: str, host: str) -> bool:
    """True when `origin` names the same port the request was sent to. An absent port means the
    scheme's default, on both sides; Origin carries the scheme and Host does not, so Origin's
    scheme decides what an absent Host port means. Anything malformed does not match."""
    try:
        parts = urlsplit(origin)
        scheme = parts.scheme.lower()
        if scheme not in _DEFAULT_PORTS:
            return False
        default = _DEFAULT_PORTS[scheme]
        origin_port = parts.port or default
        host_port = urlsplit("//" + host).port or default
    except ValueError:  # an unclosed bracket, a port that is not a number or is out of range
        return False
    return origin_port == host_port


class LocalOnly:
    """Pure ASGI middleware, so it also sees the requests no route matches."""

    def __init__(self, app: ASGIApp, allowed_hosts: Iterable[str]) -> None:
        self.app = app
        self.allowed = normalise_hosts(allowed_hosts)

    def _host_of(self, value: str) -> str | None:
        return _hostname("//" + value) if value else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if self._host_of(headers.get("host", "")) not in self.allowed:
            await self._refuse(send, 421, "host not allowed", scope["method"])
            return
        if scope["method"] in _WRITES:
            origin = headers.get("origin")
            if (
                origin is not None
                and origin != "null"
                and (
                    self._host_of_origin(origin) not in self.allowed
                    or not _origin_matches_host(origin, headers.get("host", ""))
                )
            ):
                await self._refuse(send, 403, "cross-origin request refused", scope["method"])
                return
            if origin == "null" or headers.get("sec-fetch-site") == "cross-site":
                await self._refuse(send, 403, "cross-origin request refused", scope["method"])
                return
        await self.app(scope, receive, send)

    @staticmethod
    def _host_of_origin(origin: str) -> str | None:
        return _hostname(origin)

    async def _refuse(self, send: Send, status: int, detail: str, method: str) -> None:
        # Never log the offending host or origin: they are chosen by whoever sent the request.
        log.warning("request refused", extra={"reason": detail, "method": method, "status": status})
        body = json.dumps({"detail": detail}).encode()
        start: Message = {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"),
            ],
        }
        await send(start)
        await send({"type": "http.response.body", "body": body})
