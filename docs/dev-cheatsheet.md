# Developer Cheatsheet

Daily commands, workflows, and concepts for Commerce-OS. Commands assume the repo root and `uv`.

---

## 1. Daily loop

```bash
uv sync                    # install / sync dependencies
uv run ruff format .       # format
uv run ruff check .        # lint
uv run pytest -q           # tests
uv run fastapi dev app/main.py
```

Before pushing:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
uv run alembic check
```

CI runs lint, format checks, and tests on Python 3.13 and 3.14.

---

## 2. Environment and settings

`.env` is git-ignored. `.env.example` is the template.

```bash
touch .env
# fill in DATABASE_URL, REDIS_URL, JWT_SECRET, JWT_ALGORITHM, JWT_ACCESS_TOKEN_EXPIRE_MINUTES
```

Key rules:

- Settings are loaded lazily through `get_settings()`; importing config should not require env vars.
- `get_settings()` is cached. Tests that change env vars should call `get_settings.cache_clear()`.
- The `.env` path is absolute, so it works from any working directory.
- Pydantic maps `jwt_access_token_expire_minutes` to `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`.
- `JWT_SECRET` should be at least 32 bytes for HS256.
- `DATABASE_URL` must match the compose host port (`5433`, not `5432`).

```python
from app.configs.env_settings import get_settings

settings = get_settings()
```

---

## 3. Docker services

Postgres is exposed on host `5433`; Redis on `6379`.

```bash
docker compose up -d
docker compose ps
docker compose logs -f postgres
docker compose logs -f redis
docker compose down
docker compose down -v       # also deletes volumes/data
```

Load `.env` into the shell for psql/redis commands:

```bash
set -a && . ./.env && set +a
```

Postgres:

```bash
docker compose exec -T postgres pg_isready \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB"

docker compose exec -T postgres psql \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

Useful psql commands:

```sql
\dt                  -- tables
\d users             -- users schema
\d+ users            -- more detail
select * from users;
```

Redis:

```bash
docker compose exec -T redis sh -c 'redis-cli -a "$REDIS_PASSWORD" ping'
# PONG
```

Port conflict fix: change only the host side in `docker-compose.yml`, then update `DATABASE_URL`.

```yaml
ports:
  - "5433:5432"
```

---

## 4. Database and SQLAlchemy

```python
from app.configs.db_connection import Base, get_db, get_engine, get_session_factory
```

Concepts:

- `Base` is the declarative base. All models inherit from it.
- `get_engine()` and `get_session_factory()` are cached; one engine/pool per process.
- `get_db()` yields a `Session` and always closes it.
- `pool_pre_ping=True` checks stale connections before use.
- `autoflush=False` means queries do not auto-flush pending changes.
- Sessions are short-lived; do not share them across requests.

Inspect the schema:

```bash
uv run python -c "
from sqlalchemy import inspect
from app.configs.db_connection import get_engine
print(inspect(get_engine()).get_table_names())
"
```

Check connectivity:

```bash
uv run python -c "
from sqlalchemy import text
from app.configs.db_connection import get_engine
with get_engine().connect() as c:
    print(c.execute(text('select 1')).scalar())
"
```

---

## 5. Alembic workflow

### 5.1 One-time setup (already done in this repo)

```bash
uv run alembic init migrations
```

`migrations/env.py` must:

- import `Base` and every model module;
- set `target_metadata = Base.metadata`;
- load the database URL from settings;
- escape `%` in the URL because Alembic uses `ConfigParser`.

```python
from app.configs.db_connection import Base
from app.configs.env_settings import get_settings
import app.models.user_model  # noqa: F401
import app.models.catalog_model  # noqa: F401
import app.models.cart_model  # noqa: F401

config = context.config
config.set_main_option(
    "sqlalchemy.url",
    get_settings().database_url.replace("%", "%%"),
)
target_metadata = Base.metadata
```

`alembic.ini` needs:

```ini
script_location = migrations
prepend_sys_path = .
```

### 5.2 The normal change loop

```bash
# 1. Ensure the DB is running and at head
docker compose up -d postgres
uv run alembic upgrade head

# 2. Change SQLAlchemy models

# 3. Generate a migration
uv run alembic revision --autogenerate -m "add inventory table"

# 4. Review migrations/versions/<rev>_add_inventory_table.py
#    Check types, nullable, defaults, indexes, FKs, and downgrade()

# 5. Apply
uv run alembic upgrade head

# 6. Verify
uv run alembic current
```

Rules:

- Never edit a migration that has already been applied. Add a new one.
- One logical change per migration.
- Always review autogenerate output.
- Autogenerate does not detect renames; it sees a drop plus an add.
- Commit model changes and the migration together.
- Use `alembic stamp head` only when adopting an existing schema.

### 5.3 Inspection commands

```bash
uv run alembic current                 # applied revision
uv run alembic heads                   # latest revision(s)
uv run alembic branches                # branch points
uv run alembic history --verbose       # full history
uv run alembic show <revision>         # details for one revision
```

### 5.4 Upgrade and downgrade

```bash
uv run alembic upgrade head            # apply all
uv run alembic upgrade +1              # apply one
uv run alembic downgrade -1            # roll back one
uv run alembic downgrade base          # roll back everything (dev only)
```

Round-trip check on a dev database:

```bash
uv run alembic downgrade -1
uv run alembic upgrade head
```

### 5.5 Drift and offline SQL

```bash
uv run alembic check                   # models changed without a migration?
uv run alembic upgrade head --sql      # print SQL without applying
```

`alembic check` is a good CI gate. Run it after `upgrade head`.

### 5.6 Multiple heads

```bash
uv run alembic heads
uv run alembic merge -m "merge heads" <rev1> <rev2>
uv run alembic upgrade head
```

### 5.7 Migration recipes

**Add a nullable column**

```python
op.add_column("users", sa.Column("nickname", sa.String(255), nullable=True))
```

**Add a non-null column to an existing table**

Use a server default so existing rows can be backfilled:

```python
op.add_column(
    "users",
    sa.Column("role", sa.String(20), server_default="customer", nullable=False),
)
```

**Add a check constraint**

```python
op.create_check_constraint(
    "ck_users_role",
    "users",
    "role IN ('customer', 'admin')",
)
```

Drop it with:

```python
op.drop_constraint("ck_users_role", "users", type_="check")
```

**Constraint naming**

| Prefix | Meaning | Example |
| --- | --- | --- |
| `pk` | primary key | `pk_users` |
| `fk` | foreign key | `fk_orders_user_id_users` |
| `uq` | unique | `uq_users_email` |
| `ck` | check | `ck_users_role` |
| `ix` | index | `ix_users_email` |

Explicit names make migrations readable and `drop_constraint` reliable.

**Enum columns**

Prefer a non-native enum with a check constraint:

```python
role: Mapped[UserRole] = mapped_column(
    Enum(
        UserRole,
        name="ck_users_role",
        native_enum=False,
        create_constraint=True,
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
        length=20,
    ),
    nullable=False,
    default=UserRole.CUSTOMER,
    server_default="customer",
)
```

`values_callable` is important: without it SQLAlchemy stores member names (`CUSTOMER`) instead of values (`customer`).

**UUID primary keys**

```python
from uuid import UUID, uuid4
from sqlalchemy import Uuid

id: Mapped[UUID] = mapped_column(
    Uuid(as_uuid=True),
    primary_key=True,
    default=uuid4,
)
```

Changing an existing integer primary key to UUID is not a simple `ALTER COLUMN`. On a dev database with no data:

```bash
uv run alembic downgrade base
# update the model and regenerate the migration
uv run alembic upgrade head
```

With data, add a new UUID column, backfill with `gen_random_uuid()`, drop the old key, rename, and recreate the primary key. Do not let autogenerate produce a naive `alter_column`; Postgres will reject it.

**SQLite tests and batch mode**

If tests run on SQLite, configure Alembic with batch rendering:

```python
context.configure(
    connection=connection,
    target_metadata=target_metadata,
    render_as_batch=True,
)
```

---

## 6. Testing

Current suites: `tests/test_auth_mvp.py` (10 tests), `tests/test_catalog_mvp.py` (16), `tests/test_catalog_admin.py` (5), and `tests/test_cart_mvp.py` (16) — 47 total. See [`testing.md`](testing.md) for the suites and [`testing-waitlist.md`](testing-waitlist.md) for future coverage.

```bash
uv run pytest -q                    # all tests
uv run pytest tests/test_auth_mvp.py -q # auth suite
uv run pytest tests/test_cart_mvp.py -q # cart suite
uv run pytest -q -k "login"         # by name
uv run pytest -q -x                 # stop on first failure
uv run pytest -q --lf               # last failed
uv run pytest -q -s                 # show prints
uv run pytest --collect-only -q     # list tests
```

Optional coverage:

```bash
uv add --dev pytest-cov
uv run pytest --cov=app --cov-report=term-missing
```

### API tests

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_register() -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    assert response.status_code == 201
```

### Database test isolation

Use a transaction and roll it back:

```python
import pytest
from sqlalchemy.orm import Session

from app.configs.db_connection import get_engine


@pytest.fixture
def db_session():
    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
```

Override the FastAPI dependency when needed:

```python
app.dependency_overrides[get_db] = lambda: db_session
```

### Auth token tests

```python
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt

from app.configs.env_settings import get_settings

settings = get_settings()

expired = jwt.encode(
    {"sub": str(uuid4()), "exp": datetime.now(UTC) - timedelta(minutes=1)},
    settings.jwt_secret,
    algorithm=settings.jwt_algorithm,
)
```

Expected behavior:

| Case | Status |
| --- | --- |
| Valid token | `200` |
| Missing token | `401` |
| Malformed token | `401` |
| Expired token | `401` |
| Unknown user | `401` |
| Authenticated but not admin | `403` |

### Migration tests in CI

Against a disposable Postgres service:

```bash
uv run alembic upgrade head
uv run alembic check
uv run alembic downgrade -1
uv run alembic upgrade head
```

---

## 7. Auth and security notes

- Passwords are hashed with `pwdlib` (Argon2). Never store plaintext.
- JWT `sub` must be a string, even when user IDs are UUIDs: `str(user.id)`.
- Parse `sub` with `UUID(...)` if the primary key is a UUID; catch `ValueError`.
- Catch `jwt.InvalidTokenError`; it is not a `ValueError`.
- Return the same `"Invalid credentials"` message for unknown email and wrong password.
- Send `WWW-Authenticate: Bearer` on `401`.
- Keep the role out of the JWT for authorization. Load the user and check `current_user.role` from the database.
- Public registration must never accept a `role` field.
- Use `409` for duplicate email/username, and handle `IntegrityError` to cover races.
- `require_admin` belongs in a dependency, not in each route.

---

## 8. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `ImportError: cannot import name 'router'` | `app/api/routes/__init__.py` is empty; export `router` or import from `auth_routes` directly. |
| `AttributeError: module 'jwt' has no attribute 'InvalidTokeError'` | Typo; use `jwt.InvalidTokenError`. |
| `AttributeError: 'Settings' object has no attribute 'access_token_expire_minutes'` | Field is `jwt_access_token_expire_minutes`. |
| `InsecureKeyLengthWarning` | `JWT_SECRET` is under 32 bytes. |
| `invalid input syntax for type uuid` | An integer ID or JWT `sub` reached a UUID column. |
| `column "id" cannot be cast automatically to type uuid` | Hand-write the migration or reset the dev database. |
| `OCI runtime exec failed: exec: " pg_isready"` | Leading space or quoted whole command; pass binary and args separately. |
| `pg_isready: no response` | Postgres still starting; check `docker compose ps` and logs. |
| `ruff format --check` fails | Run `uv run ruff format .`. |
| `alembic check` reports changes | Model changed without a migration, or DB is not at head. |
| `ModuleNotFoundError: psycopg` | Run `uv sync`; `psycopg` is a project dependency. |
| `password authentication failed` | `.env` credentials and the existing Postgres volume disagree. `docker compose down -v` resets dev data. |

---

## 9. Concepts learned in this session

- **Layered boundaries:** routers handle HTTP, services hold business rules, repositories handle persistence, models define schema.
- **Dependency injection:** FastAPI dependencies keep routers thin and make auth/DB setup reusable.
- **Import-time side effects:** loading settings or creating engines at module import makes tests and CI fragile. Resolve them lazily.
- **Caching:** `@cache` is appropriate for zero-argument factories such as settings, engines, and session factories.
- **Alembic compares metadata to the database:** models must be imported before autogenerate, and migrations must be reviewed.
- **Migration history is append-only:** applied migrations are immutable; schema changes go in new revisions.
- **Autogenerate is a draft:** it misses renames and cannot safely convert integer IDs to UUIDs.
- **Constraints are part of the API:** unique email, role checks, and foreign keys protect invariants that application checks can race past.
- **Enum storage is surprising:** SQLAlchemy stores enum names unless `values_callable` is provided.
- **UUIDs are strings in JSON and JWT:** the database type changes, but `sub` remains a string.
- **401 vs 403:** `401` means unauthenticated; `403` means authenticated but not allowed.
- **Generic auth errors:** distinguish valid credentials from invalid ones only in logs, not responses.
- **Healthchecks and ports:** compose healthchecks are commands; host port mappings must match `DATABASE_URL`.
- **Formatting is a CI gate:** `ruff format --check` fails the build even when `ruff check` passes.
