from datetime import UTC, datetime, timedelta
from functools import cache
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.configs.env_settings import Settings, get_settings


class SecurityControl:
    """Password hashing and JWT handling for authentication.

    Wraps pwdlib's recommended password hasher and PyJWT, configured from
    `Settings` (secret, algorithm, access-token lifetime).
    """

    def __init__(self, settings: Settings) -> None:
        """Bind the control to `settings` and create the password hasher."""
        self.settings = settings
        self.password_hash = PasswordHash.recommended()

    def hash_password(self, password: str) -> str:
        """Return a salted hash of `password` (Argon2 by default)."""
        return self.password_hash.hash(password)

    def verify_password(self, password: str, hashed_password: str) -> bool:
        """Return `True` when `password` matches `hashed_password`."""
        return self.password_hash.verify(password, hashed_password)

    def create_access_token(self, user_id: UUID) -> str:
        """Return a signed JWT for `user_id`.

        The payload holds `sub` (the UUID as a string) and `exp` (now plus
        `jwt_access_token_expire_minutes`).
        """
        expires_at = datetime.now(UTC) + timedelta(
            minutes=self.settings.jwt_access_token_expire_minutes
        )
        payload = {"sub": str(user_id), "exp": expires_at}
        return jwt.encode(
            payload, self.settings.jwt_secret, algorithm=self.settings.jwt_algorithm
        )

    def verify_access_token(self, token: str) -> str | None:
        """Return the token's `sub` claim, or `None` when it is unusable.

        Rejects bad signatures, expired tokens, unexpected algorithms, and
        missing or non-string subjects.
        """
        try:
            payload = jwt.decode(
                token, self.settings.jwt_secret, algorithms=self.settings.jwt_algorithm
            )
        except jwt.InvalidTokenError:
            return None
        subject = payload.get("sub")
        return subject if isinstance(subject, str) else None


@cache
def security() -> SecurityControl:
    """Return the cached `SecurityControl` built from current settings."""
    return SecurityControl(get_settings())
