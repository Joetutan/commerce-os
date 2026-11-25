# Testing

## Current suite

Four suites run against a real Postgres database, from HTTP entry down to the schema.

### Auth (`tests/test_auth_mvp.py`, 10 tests)

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

### Catalog (`tests/test_catalog_mvp.py`, 16 tests)

| Test | What it verifies |
| --- | --- |
| `test_list_products_returns_only_active` | List excludes draft and archived products |
| `test_list_products_paginates` | `limit`/`offset` slice results and echo in the envelope |
| `test_list_products_returns_empty_page` | Empty catalog returns `200` with `items: []` and `total: 0` |
| `test_get_product_returns_active_product` | Detail by slug returns the product and its variants |
| `test_get_product_hides_inactive_products` | Draft and archived slugs return `404` (parametrized) |
| `test_get_product_unknown_slug_returns_404` | Unknown slug returns `404` |
| `test_get_variant_returns_active_variant` | Variant by SKU returns the variant |
| `test_get_variant_hides_inactive_products` | Variants of draft/archived products return `404` (parametrized) |
| `test_get_variant_unknown_sku_returns_404` | Unknown SKU returns `404` |
| `test_product_create_normalizes_slug` | `ProductCreate` trims and lowercases the slug |
| `test_product_create_allows_empty_variants` | `ProductCreate` does not require variants; they are added separately |
| `test_variant_create_rejects_negative_price` | Negative prices fail schema validation |
| `test_variant_create_rejects_lowercase_currency` | Currency must be three uppercase letters |
| `test_negative_price_violates_db_constraint` | The database check constraint rejects negative prices |

### Catalog admin (`tests/test_catalog_admin.py`, 5 tests)

| Test | What it verifies |
| --- | --- |
| `test_create_list_and_get_product` | Create returns `201` as a draft with no variants; admin list and detail work; drafts stay out of the public catalog |
| `test_update_product` | `PATCH` updates only the supplied fields and leaves the slug alone |
| `test_add_variant_and_publish` | Add variant returns `201`; publishing returns `active` and the product appears publicly |
| `test_update_and_delete_variant` | Variant `PATCH` updates price; `DELETE` returns `204` |
| `test_archive_and_delete_product` | Archive sets `archived`; `DELETE` returns `204` and the detail then returns `404` |

### Cart (`tests/test_cart_mvp.py`, 16 tests)

| Test | What it verifies |
| --- | --- |
| `test_cart_routes_require_auth` | All four cart routes return `401` without a token |
| `test_get_cart_creates_one_empty_cart` | First `GET` creates exactly one cart, returns empty aggregates (`0`, `"0.00"`, `null`), and a second `GET` reuses the same id |
| `test_add_item_returns_cart_with_live_totals` | Nested response shape, variant attributes, `line_total`, `subtotal`, and `currency` |
| `test_adding_same_variant_increments_quantity` | `POST` is a delta: the same variant stays one line and quantity grows |
| `test_two_variants_are_separate_lines` | Two variants produce two lines with combined `total_quantity` and `subtotal` |
| `test_add_unknown_variant_returns_404` | Unknown `variant_id` returns `404 "Variant not found"` |
| `test_add_variant_from_draft_product_returns_404` | Only variants of active products are addable |
| `test_line_quantity_is_capped` | Adding past `99` returns `409` and leaves the line at `99` |
| `test_add_quantity_above_schema_limit_returns_422` | Request `quantity: 100` fails schema validation |
| `test_update_item_sets_absolute_quantity` | `PATCH` sets the quantity absolutely, recomputes totals, and is idempotent on repeat |
| `test_update_item_below_schema_limit_returns_422` | `quantity: 0` is rejected; removal is `DELETE` |
| `test_update_missing_item_returns_404` | Unknown `item_id` returns `404 "Cart item not found"` |
| `test_update_without_a_cart_returns_404` | `PATCH` does not create a cart; it returns `404 "Cart not found"` |
| `test_delete_item_removes_line_and_updates_totals` | `DELETE` returns `204`, totals recompute, and a repeated delete returns `404` |
| `test_delete_without_a_cart_returns_404` | `DELETE` does not create a cart; it returns `404 "Cart not found"` |
| `test_cart_is_scoped_to_the_authenticated_user` | One user cannot see, update, or delete another user's cart lines |

Money assertions normalize with `Decimal(str(value))`, so they hold whether FastAPI serializes `Decimal` as a string or a number.

## Running the suite

Postgres must be running:

```bash
docker compose up -d postgres
```

Run the auth suite:

```bash
uv run pytest tests/test_auth_mvp.py -q
```

Run the catalog suite:

```bash
uv run pytest tests/test_catalog_mvp.py -q
```

Run the catalog admin suite:

```bash
uv run pytest tests/test_catalog_admin.py -q
```

Run the cart suite:

```bash
uv run pytest tests/test_cart_mvp.py -q
```

Run everything:

```bash
uv run pytest -q
```

Expected:

```
...............................................                          [100%]
47 passed
```

## How the test database works

`tests/conftest.py`:

- Reads `DATABASE_URL` from `.env` (or the environment) and derives a test database by appending `_test` if needed. For example, `commerce_db_dev` becomes `commerce_db_dev_test`.
- Honors `TEST_DATABASE_URL` when provided. It still appends `_test` unless the name already ends with `_test`.
- Creates the test database if it does not exist.
- Runs `alembic upgrade head` once per test session.
- Overrides `JWT_SECRET`, `JWT_ALGORITHM`, and expiry for deterministic tests.
- Truncates `cart_items`, `carts`, `product_variants`, `products`, and `users` before each test.
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
├── conftest.py            # test DB, migrations, isolation, fixtures
├── test_auth_mvp.py       # MVP auth workflow
├── test_catalog_mvp.py    # public catalog workflow
├── test_catalog_admin.py  # catalog admin happy paths
└── test_cart_mvp.py       # cart workflow and totals
```

The suites are integration-oriented: they go through FastAPI, the service layer, SQLAlchemy, and Postgres. Unit tests for individual layers are on the waitlist.

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
