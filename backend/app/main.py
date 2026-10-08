from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.middleware import request_context
from app.api.routes import agents, audit, auth, health
from app.core.config import Settings, get_settings
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
    return app


app = create_app()
