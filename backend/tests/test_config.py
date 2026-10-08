import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_default_secret() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(env="production", database_url="postgresql+psycopg://x/y")


def test_production_rejects_sqlite() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(env="production", secret_key="x" * 40, database_url="sqlite:///a.db")


def test_production_accepts_valid_config() -> None:
    s = Settings(env="production", secret_key="x" * 40, database_url="postgresql+psycopg://x/y")
    assert s.env == "production"


def test_blank_optional_settings_are_unset() -> None:
    s = Settings(
        env="production", secret_key="x" * 40, database_url="postgresql://u:p@h/db",
        bootstrap_token="", google_client_id=" ", owner_email="",
    )  # fmt: skip
    assert s.bootstrap_token is None
    assert s.google_client_id is None
    assert s.owner_email is None
