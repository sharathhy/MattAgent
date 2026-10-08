"""Password hashing and access tokens."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import Settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_access_token(subject: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> str | None:
    """Return the token subject, or None if the token is invalid or expired."""
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    sub = claims.get("sub")
    return sub if isinstance(sub, str) else None
