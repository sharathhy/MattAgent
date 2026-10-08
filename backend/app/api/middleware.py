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
    "Permissions-Policy": "camera=(), geolocation=()",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'"
#: For the web app when the API process also serves it (single-service deployments).
WEB_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://accounts.google.com/gsi/client; "
    "style-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/style; "
    "frame-src https://accounts.google.com/gsi/; "
    "connect-src 'self' https://accounts.google.com/gsi/; "
    "img-src 'self' data: https://*.googleusercontent.com; "
    "frame-ancestors 'none'"
)


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
    path = request.url.path
    if not path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers.update(SECURITY_HEADERS)
        if path.startswith("/api"):
            response.headers["Content-Security-Policy"] = API_CSP
        else:
            response.headers["Content-Security-Policy"] = WEB_CSP
            # Google Sign-In checks the page origin, which "no-referrer" would hide.
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            # The Google sign-in popup reports back with postMessage; allow that, nothing more.
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    return response
