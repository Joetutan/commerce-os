# Commerce-OS

A modular e-commerce platform for **inventory management** and **order orchestration**. Transactions are handled by a third-party provider.

> Early development - scaffold and CI are in place; domain modules are in progress.

## Domains

- **Orders** - lifecycle, line items, pricing snapshots, state transitions.
- **Cart** - pre-checkout intent: mutable line items, live pricing, conversion to an order.
- **Inventory** - stock levels, reservations, releases, availability.
- **Transactions** - payment sessions and webhooks via a third-party provider.
- **Catalog** - products, variants, pricing. Public read-only routes plus admin CRUD.
- **Identity** - accounts, authentication, and roles.

## Stack

Python 3.13+ · FastAPI · Pydantic v2 · SQLAlchemy 2.x · Alembic · PyJWT · uv · Ruff · pytest

## Quick start

```bash
uv sync
touch .env   # DATABASE_URL, REDIS_URL, JWT_SECRET
uv run fastapi dev app/main.py
```

Docs at `http://127.0.0.1:8000/docs`.

## Layout

```
app/api/          routers
app/configs/      settings, database, security
app/models/       SQLAlchemy models
app/repository/   persistence
app/schemas/      request/response models
app/service/      business rules and orchestration
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

Testing: [`docs/testing.md`](docs/testing.md) covers the auth, catalog, catalog admin, and cart suites; [`docs/testing-waitlist.md`](docs/testing-waitlist.md) tracks future coverage.

Catalog: [`docs/catalog-todo.md`](docs/catalog-todo.md) tracks the remaining catalog follow-ups.

Cart: [`docs/cart-todo.md`](docs/cart-todo.md) documents phase one.

Orders: [`docs/orders-todo.md`](docs/orders-todo.md) plans checkout and lifecycle.

Sessions: [`docs/sessions-and-concurrency.md`](docs/sessions-and-concurrency.md) maps request-scoped sessions, transaction boundaries, and the concurrency trade-offs behind the cart.

## Configuration

Set in `.env` (git-ignored):

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy connection string. |
| `REDIS_URL` | Redis connection string (required by settings). |
| `JWT_SECRET` | Token signing key. |
| `PAYMENT_PROVIDER_API_KEY` | Provider credential. |
| `PAYMENT_PROVIDER_WEBHOOK_SECRET` | Webhook signature verification. |

`PAYMENT_PROVIDER_*` is reserved for the planned Transactions domain and is not read by the app yet.

## Roadmap

- [x] Scaffold and CI
- [x] Database session and Alembic baseline
- [x] JWT authentication
- [x] Catalog models and public routes
- [x] Catalog admin endpoints
- [x] Cart phase one
  - [x] `carts` and `cart_items` models + migration
  - [x] Cart routes: read, add, update, remove
  - [x] Live pricing and totals
  - [x] Cart happy-path tests
- [ ] Orders and checkout (convert cart to order)
- [ ] Order state machine
- [ ] Inventory stock levels
- [ ] Inventory reservations
- [ ] Provider integration and webhooks
- [ ] Multi-currency pricing and conversion

## License

TBD.
