"""Encryption at rest for sensitive owner data (bank account numbers, UPI IDs).

The key is derived from MATT_SECRET_KEY, which lives only in the hosting environment. Changing
that secret makes stored account details unreadable; re-enter them in Settings if you rotate it.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings


def _fernet(settings: Settings) -> Fernet:
    digest = hashlib.sha256(b"matt-receiving-accounts:" + settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(settings: Settings, value: str) -> str:
    return _fernet(settings).encrypt(value.encode()).decode()


def decrypt(settings: Settings, token: str) -> str | None:
    try:
        return _fernet(settings).decrypt(token.encode()).decode()
    except InvalidToken:
        return None  # the secret key changed since this was saved
