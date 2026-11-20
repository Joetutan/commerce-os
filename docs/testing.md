# Testing

## Current suite

The MVP auth suite lives in `tests/test_auth_mvp.py` and covers the flow from HTTP entry to the database.

| Test | What it verifies |
| --- | --- |
| `test_register_success` | `201`, response shape, UUID, hashed password, `customer` role in Postgres |
| `test_register_rejects_invalid_email` | `422` with `loc == ["body", "email"]` |
| `test_register_rejects_duplicate_email` | `409` for an existing email |
| `test_login_success` | `200`, `token_type == "bearer"`, JWT `sub` matches the user UUID |
| `test_login_rejects_wrong_password` | `401` with the generic message |
| `test_login_unknown_email_matches_wrong_password` | Unknown email and wrong password return identical responses |
| `test_me_with_valid_token` | `200` and the correct `id`, `username`, `email` |
| `test_me_rejects_malformed_token` | `401` with `WWW-Authenticate: Bearer` |
| `test_me_rejects_expired_token` | `401` for an expired JWT |
| `test_duplicate_email_violates_db_constraint` | The database unique constraint rejects duplicates |

## Running the suite

Postgres must be running:

```bash
docker compose up -d postgres
```

Run the auth suite:

```bash
uv run pytest tests/test_auth_mvp.py -q
```

Run everything:

```bash
uv run pytest -q
```

Expected:

```
..........                                                               [100%]
10 passed
```

## How the test database works

`tests/conftest.py`:

- Reads `DATABASE_URL` from `.env` (or the environment) and derives a test database by appending `_test` if needed. For example, `commerce_db_dev` becomes `commerce_db_dev_test`.
- Honors `TEST_DATABASE_URL` when provided. It still appends `_test` unless the name already ends with `_test`.
- Creates the test database if it does not exist.
- Runs `alembic upgrade head` once per test session.
- Overrides `JWT_SECRET`, `JWT_ALGORITHM`, and expiry for deterministic tests.
- Truncates `users` before each test.
- Provides `client` (TestClient) and `db_session` fixtures.

The test database is separate from the development database. Tests never write to `commerce_db_dev`.

To point at a different server:

```bash
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5433/commerce_db uv run pytest -q
```

The name becomes `commerce_db_test`.

## Why Postgres, not SQLite

- The schema uses native `UUID` columns.
- Role checks use a database `CHECK` constraint.
- `created_at` uses a server-side default.
- Unique-constraint behavior is part of the suite.

SQLite would require batch migrations and would not exercise the same constraints.

## Test structure

```
tests/
├── conftest.py          # test DB, migrations, isolation, fixtures
└── test_auth_mvp.py     # MVP auth workflow
```

The suite is integration-oriented: it goes through FastAPI, the service layer, SQLAlchemy, and Postgres. Unit tests for individual layers are on the waitlist.

## CI

CI runs lint, format checks, and the test suite with a Postgres 16 service container. The workflow sets `DATABASE_URL`, `REDIS_URL`, and JWT test values. `tests/conftest.py` creates `commerce_db_test` inside that service and applies migrations.

```yaml
services:
  postgres:
    image: postgres:16
    env:
      POSTGRES_USER: commerce_user
      POSTGRES_PASSWORD: commerce_password
      POSTGRES_DB: commerce_db
    ports:
      - 5432:5432
    options: >-
      --health-cmd "pg_isready -U commerce_user -d commerce_db"
      --health-interval 5s
      --health-timeout 5s
      --health-retries 10
```

The service user must be allowed to create the `commerce_db_test` database. The default Postgres superuser is, so the stock image works.

## Future coverage

The remaining tests are tracked in [`testing-waitlist.md`](testing-waitlist.md).
