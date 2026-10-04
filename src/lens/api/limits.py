"""Request body size limit for uploads, enforced on streamed bytes (works for chunked bodies)."""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestTooLarge(Exception):
    """Raised from `receive` once the body passes the limit; mapped to a 413 response."""


async def request_too_large_handler(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse({"detail": "request too large"}, status_code=413)


class BodySizeLimit:
    """Pure ASGI middleware: rejects `POST <path>` bodies over `max_bytes`.

    A declared Content-Length over the limit is refused up front; otherwise the bytes actually
    received are counted, so a chunked body (no Content-Length) is stopped too.
    """

    def __init__(self, app: ASGIApp, max_bytes: int, path: str = "/batches") -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.path = path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/") != self.path
        ):
            await self.app(scope, receive, send)
            return

        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.max_bytes:
            await request_too_large_response(scope, receive, send)
            return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestTooLarge
            return message

        await self.app(scope, counting_receive, send)


async def request_too_large_response(scope: Scope, receive: Receive, send: Send) -> None:
    response = JSONResponse({"detail": "request too large"}, status_code=413)
    await response(scope, receive, send)
