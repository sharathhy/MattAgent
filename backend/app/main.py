from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker

from app.api.middleware import request_context
from app.api.routes import agents, audit, auth, business, changes, health, ops, payments
from app.core.config import Settings, get_settings
from app.core.google import GoogleTokenVerifier
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimiter
from app.db.session import build_engine
from app.llm.router import ModelRouter
from app.services import tools
from app.services.errors import ServiceError
from app.worker import Worker


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level, settings.log_json)
        engine = build_engine(settings.database_url)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as db:
            tools.seed_tools(db)
        worker = None
        if settings.worker_enabled:
            worker = Worker(
                factory,
                app.state.model_router,
                settings.worker_poll_seconds,
                settings.worker_threads,
            )
            worker.start()
        try:
            yield
        finally:
            if worker:
                worker.stop()
            engine.dispose()

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
    app.state.model_router = ModelRouter(settings)
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

    for router in (
        health.router,
        auth.router,
        agents.router,
        audit.router,
        ops.router,
        business.router,
        payments.router,
        changes.router,
    ):
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
