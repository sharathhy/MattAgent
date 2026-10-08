"""Verify Google Sign-In ID tokens (Google Identity Services).

Only the OAuth client id is needed; it is public. The token's signature is checked against
Google's published keys, and its audience, issuer, expiry and email verification are enforced.
"""

from dataclasses import dataclass
from typing import Protocol

import jwt

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class SigningKeySource(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK: ...


@dataclass(frozen=True)
class GoogleIdentity:
    email: str
    name: str


class GoogleTokenError(ValueError):
    pass


class GoogleTokenVerifier:
    def __init__(self, client_id: str, keys: SigningKeySource | None = None) -> None:
        self.client_id = client_id
        self.keys = keys or jwt.PyJWKClient(GOOGLE_CERTS_URL, cache_keys=True)

    def verify(self, credential: str) -> GoogleIdentity:
        try:
            key = self.keys.get_signing_key_from_jwt(credential)
            claims = jwt.decode(
                credential,
                key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=GOOGLE_ISSUERS,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise GoogleTokenError(f"Invalid Google credential: {exc}") from exc
        email = claims.get("email")
        if not isinstance(email, str) or claims.get("email_verified") is not True:
            raise GoogleTokenError("Google account email is not verified")
        return GoogleIdentity(email=email.lower(), name=str(claims.get("name", "")))
