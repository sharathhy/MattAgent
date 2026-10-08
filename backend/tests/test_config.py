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
