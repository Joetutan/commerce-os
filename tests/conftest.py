"""Shared fixtures: a disposable Postgres test database, isolation, and clients.

The test database name is the configured database plus `_test`, so the
development database is never touched.
"""

import os
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql as psycopg_sql
from sqlalchemy import text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def _read_env_file() -> dict[str, str]:
    """Parse `.env` into a dict without importing application settings."""
    path = ROOT / ".env"
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


_ENV = _read_env_file()
_BASE_URL = (
    os.getenv("TEST_DATABASE_URL")
    or _ENV.get("DATABASE_URL")
    or os.getenv("DATABASE_URL")
)

if not _BASE_URL:
    raise RuntimeError("Set TEST_DATABASE_URL or DATABASE_URL to run the test suite.")

_BASE = make_url(_BASE_URL)
_DB_NAME = _BASE.database or "commerce_db"
if not _DB_NAME.endswith("_test"):
    _DB_NAME = f"{_DB_NAME}_test"

TEST_DATABASE_URL = _BASE.set(database=_DB_NAME).render_as_string(hide_password=False)

# These must be set before importing app modules, which load settings at first use.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 32
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["REDIS_URL"] = _ENV.get("REDIS_URL", "redis://localhost:6379/0")


def _ensure_test_database() -> None:
    """Create the test database if it does not already exist."""
    url = make_url(TEST_DATABASE_URL)
    with psycopg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname="postgres",
        autocommit=True,
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (url.database,),
        ).fetchone()
        if not exists:
            connection.execute(
                psycopg_sql.SQL("CREATE DATABASE {}").format(
                    psycopg_sql.Identifier(url.database)
                )
            )


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_database() -> None:
    """Create the test database and apply Alembic migrations once per run."""
    _ensure_test_database()

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
def _clean_database(_migrate_test_database: None) -> None:
    """Truncate `users` before each test so tests stay order-independent."""
    from app.configs.db_connection import get_engine

    with get_engine().begin() as connection:
        connection.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))


@pytest.fixture
def client():
    """Yield a `TestClient` wired to the test database."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    """Yield a session for asserting directly against the test database."""
    from sqlalchemy.orm import Session

    from app.configs.db_connection import get_engine

    with Session(get_engine()) as session:
        yield session
