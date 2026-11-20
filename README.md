# Commerce-OS

A modular e-commerce platform for **inventory management** and **order orchestration**. Transactions are handled by a third-party provider.

> Early development - scaffold and CI are in place; domain modules are in progress.

## Domains

- **Orders** - lifecycle, line items, pricing snapshots, state transitions.
- **Inventory** - stock levels, reservations, releases, availability.
- **Transactions** - payment sessions and webhooks via a third-party provider.
- **Catalog** *(planned)* - products, variants, pricing.
- **Identity** *(planned)* - customer and staff accounts.

## Stack

Python 3.13+ · FastAPI · Pydantic v2 · SQLAlchemy 2.x · Alembic · PyJWT · uv · Ruff · pytest

## Quick start

```bash
uv sync
touch .env   # DATABASE_URL, JWT_SECRET, provider keys
uv run fastapi dev app/main.py
```

Docs at `http://127.0.0.1:8000/docs`.

## Layout

```
app/api/          routers and schemas
app/service/      business rules and orchestration
app/repository/   persistence
app/models/       SQLAlchemy models
app/utils/        shared helpers
migrations/       Alembic migrations
tests/            test suite
docs/             developer cheatsheet
```

## Commands

```bash
uv run pytest -q                    # tests
uv run ruff check .                 # lint
uv run ruff format .                # format
uv run alembic upgrade head         # migrations
uv run alembic revision --autogenerate -m "change"
```

CI runs lint, format checks, and tests on Python 3.13 and 3.14.

See [`docs/dev-cheatsheet.md`](docs/dev-cheatsheet.md) for the full daily toolbox: settings, Docker, SQLAlchemy, Alembic, testing, auth checks, and troubleshooting.

Testing: [`docs/testing.md`](docs/testing.md) covers the current auth suite; [`docs/testing-waitlist.md`](docs/testing-waitlist.md) tracks future coverage.

## Configuration

Set in `.env` (git-ignored):

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy connection string. |
| `JWT_SECRET` | Token signing key. |
| `PAYMENT_PROVIDER_API_KEY` | Provider credential. |
| `PAYMENT_PROVIDER_WEBHOOK_SECRET` | Webhook signature verification. |

## Roadmap

- [x] Scaffold and CI
- [ ] Database session and Alembic baseline
- [ ] Catalog and inventory models
- [ ] Inventory reservations
- [ ] Provider integration and webhooks
- [ ] Order state machine
- [ ] JWT authentication

## License

TBD.
