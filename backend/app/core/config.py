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

    # --- AI model router (free-first). Keys come only from the environment. ---
    gemini_api_key: str | None = None
    #: Alias Google keeps pointed at its current free-tier Flash model.
    gemini_model: str = "gemini-3.8-flash"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    #: More free tiers the Free Model Scout can use (see app/llm/free_sources.py). Empty model
    #: names let MATT pick the best free model itself.
    openrouter_api_key: str | None = None
    openrouter_model: str = ""
    cerebras_api_key: str | None = None
    cerebras_model: str = ""
    mistral_api_key: str | None = None
    mistral_model: str = "mistral-small-latest"
    ollama_url: str | None = None
    ollama_model: str = "llama3.2"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    #: Premium (paid) models are only used when explicitly allowed.
    allow_premium_models: bool = False
    #: Hard rule: only free and local models are ever called. Paid providers are not even built.
    free_models_only: bool = True
    #: Spend limits for paid model usage, in INR. MATT stops and asks for approval at the limit.
    daily_ai_budget_inr: float = Field(default=0, ge=0)
    monthly_ai_budget_inr: float = Field(default=0, ge=0)
    usd_to_inr: float = Field(default=84.0, gt=0)
    #: Where customers pay: the owner's own UPI ID (for example a PhonePe UPI ID). Set it only in
    #: the hosting environment. MATT is receive-only: it never sends or debits money.
    upi_id: str | None = None
    upi_payee_name: str = "MATT"
    #: Change requests: MATT opens pull requests on its own repository with this fine-grained
    #: token (this repository only; Contents + Pull requests). It never merges.
    github_token: str | None = None
    github_repo: str = "sharathhy/MattAgent"
    github_base_branch: str = "claude/matt-foundation-cnz4ei"
    #: Business timezone: decides what "today" means for revenue.
    timezone: str = "Asia/Kolkata"

    # --- Background worker ---
    worker_enabled: bool = True
    worker_poll_seconds: float = Field(default=1.0, gt=0)

    login_rate_limit: int = Field(default=10, ge=1, description="Login attempts per window")
    login_rate_window_seconds: int = Field(default=60, ge=1)

    @field_validator(
        "bootstrap_token",
        "google_client_id",
        "owner_email",
        "static_dir",
        "gemini_api_key",
        "groq_api_key",
        "openrouter_api_key",
        "cerebras_api_key",
        "mistral_api_key",
        "upi_id",
        "github_token",
        "ollama_url",
        "anthropic_api_key",
        mode="before",
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
