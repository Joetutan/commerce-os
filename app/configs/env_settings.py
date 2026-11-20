from functools import cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Application settings sourced from the environment or `.env`.

    Field names map to upper-case variables, so `database_url` reads
    `DATABASE_URL`. Unknown variables are ignored.
    """

    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@cache
def get_settings() -> Settings:
    """Return the cached settings instance.

    Because it is cached, changing `.env` requires a process restart.
    """
    return Settings()
