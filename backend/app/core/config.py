"""Application settings, loaded from environment variables (prefix ``MATT_``)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
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

    login_rate_limit: int = Field(default=10, ge=1, description="Login attempts per window")
    login_rate_window_seconds: int = Field(default=60, ge=1)

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.env == "production":
            if self.secret_key == _INSECURE_DEFAULT_SECRET or len(self.secret_key) < 32:
                raise ValueError(
                    "MATT_SECRET_KEY must be set to a 32+ character value in production"
                )
            if self.database_url.startswith("sqlite"):
                raise ValueError("Use PostgreSQL (MATT_DATABASE_URL) in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
