from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.middleware import request_context
from app.api.routes import agents, audit, auth, health
from app.core.config import Settings, get_settings
from app.core.google import GoogleTokenVerifier
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimiter
from app.services.errors import ServiceError


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level, settings.log_json)
        yield

    app = FastAPI(
        title="MATT API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.env == "production" else "/docs",
        redoc_url=None,
    )
    app.state.login_limiter = RateLimiter(
        settings.login_rate_limit, settings.login_rate_window_seconds
    )
    app.state.google_verifier = (
        GoogleTokenVerifier(settings.google_client_id) if settings.google_client_id else None
    )

    app.middleware("http")(request_context)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    for router in (health.router, auth.router, agents.router, audit.router):
        app.include_router(router, prefix=settings.api_prefix)
    if settings.static_dir:
        _serve_frontend(app, Path(settings.static_dir), settings.api_prefix)
    return app


def _serve_frontend(app: FastAPI, root: Path, api_prefix: str) -> None:
    """Serve the built SPA: real files as-is, every other non-API path gets index.html."""
    root = root.resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"MATT_STATIC_DIR has no index.html: {root}")
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith(api_prefix.strip("/") + "/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        candidate = (root / path).resolve()
        if path and candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
