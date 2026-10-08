import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.core.logging import request_id_var

log = logging.getLogger("matt.http")

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "camera=(), geolocation=()",
}


async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Assign a request id, log the request, and add security headers."""
    incoming = request.headers.get("x-request-id", "")
    rid = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    log.info(
        "request",
        extra={
            "request_id": rid, "method": request.method, "path": request.url.path,
            "status": response.status_code, "duration_ms": duration_ms,
        },
    )  # fmt: skip
    response.headers["X-Request-ID"] = rid
    if not request.url.path.startswith(("/docs", "/redoc")):
        response.headers.update(SECURITY_HEADERS)
    return response
