"""Application settings, loaded from environment variables (prefix ``MATT_``)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT_SECRET = "dev-insecure-secret-change-me-before-deploying"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MATT_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    app_name: str = "MATT"
    api_prefix: str = "/api"

    database_url: str = "sqlite:///./matt.db"
    secret_key: str = _INSECURE_DEFAULT_SECRET
    access_token_minutes: int = Field(default=60, ge=5, le=24 * 60)
    jwt_algorithm: str = "HS256"

    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"
    log_json: bool = True

    #: Setup code required to create the owner account through the web UI. In production the web
    #: bootstrap is disabled unless this is set; ``matt create-owner`` always works.
    bootstrap_token: str | None = None
    #: Google OAuth client id (public) enabling "Sign in with Google".
    google_client_id: str | None = None
    #: The owner's email. The first Google sign-in with this verified email becomes the owner;
    #: no other account can claim ownership.
    owner_email: str | None = None
    #: Built frontend to serve from the API process (single-service deployments).
    static_dir: str | None = None

    login_rate_limit: int = Field(default=10, ge=1, description="Login attempts per window")
    login_rate_window_seconds: int = Field(default=60, ge=1)

    @field_validator(
        "bootstrap_token", "google_client_id", "owner_email", "static_dir", mode="before"
    )
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """Hosting dashboards often store unused variables as empty strings."""
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, url: str) -> str:
        """Hosting providers hand out ``postgres://`` URLs; SQLAlchemy needs an explicit driver."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.env == "production":
            if self.secret_key == _INSECURE_DEFAULT_SECRET or len(self.secret_key) < 32:
                raise ValueError(
                    "MATT_SECRET_KEY must be set to a 32+ character value in production"
                )
            if self.database_url.startswith("sqlite"):
                raise ValueError("Use PostgreSQL (MATT_DATABASE_URL) in production")
            if self.bootstrap_token is not None and len(self.bootstrap_token) < 8:
                raise ValueError("MATT_BOOTSTRAP_TOKEN must be at least 8 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
