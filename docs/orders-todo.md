# Orders Todo

Phase one is **planned**. Orders are the financial record of a purchase; the cart is only intent. Unlike the cart, an order snapshots product and pricing data at checkout time and keeps it immutable.

Phase one is synchronous and database-only: no payment provider calls, no inventory reservation, no background jobs.

## Status

| Piece | State |
| --- | --- |
| `Order` / `OrderItem` models | Planned |
| Alembic migration | Planned |
| Request/response schemas | Planned |
| `OrderRepository` | Planned |
| `OrderService` (checkout + lifecycle) | Planned |
| Customer routes (`/api/v1/orders`) | Planned |
| Admin routes (`/api/v1/admin/orders`) | Planned |
| Integration tests (`tests/test_order_mvp.py`) | Planned |
| Docs | This file; suite docs pending |

See [`sessions-and-concurrency.md`](sessions-and-concurrency.md) for the session, transaction, and locking reasoning that the checkout step builds on.

## Architecture at a glance

Everything implemented so far, plus the order pieces planned here. `*` marks code that this document adds; everything else already exists.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                                  HTTP clients                                │
│                        customer (JWT)            admin (JWT)                 │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼──────────────────────────────────────────┐
│                                    Routers                                   │
│                                                                              │
│  /api/v1/auth   /api/v1/catalog      /api/v1/cart      /api/v1/orders *      │
│                 /api/v1/admin/catalog                 /api/v1/admin/orders * │
│                                                                              │
│  Dependencies: get_current_user (any role), require_admin (admin only)       │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼──────────────────────────────────────────┐
│                                   Services                                   │
│                                                                              │
│  AuthService      CatalogService     CartService      OrderService *         │
│                   CatalogAdminService                  ├─ checkout           │
│                                                        └─ transition         │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼──────────────────────────────────────────┐
│                                 Repositories                                 │
│                                                                              │
│  UserRepository   CatalogRepository  CartRepository   OrderRepository *      │
│                   CatalogAdminRepo    ├─ get_cart_for_update *               │
│                                       └─ clear_items *                       │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼──────────────────────────────────────────┐
│                      SQLAlchemy Session (one per request)                    │
│                    repositories flush · services commit                      │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼──────────────────────────────────────────┐
│                                  PostgreSQL                                  │
│                                                                              │
│  users          products / product_variants                                  │
│  carts / cart_items                    orders / order_items *                │
└──────────────────────────────────────────────────────────────────────────────┘

Future, not wired yet:
  Inventory     ──►  availability check + reservation inside checkout
  Transactions  ──►  payment_status, kept separate from OrderStatus
```

### Checkout: one transaction

`OrderService` is the only place where cart and order repositories meet. The route calls one method; everything below happens inside a single transaction and one final commit.

```text
POST /api/v1/orders
  │
  └─ OrderService.checkout(user_id)
       1. CartRepository.get_cart_for_update()      SELECT ... FOR UPDATE (locks the cart row)
       2. validate: cart not empty, products active, one currency
       3. OrderRepository.create_order() + items     snapshot names, SKU, attributes, price
       4. CartRepository.clear_items()               bulk DELETE of cart_items
       5. repository.commit()                        order exists, cart empty, or nothing changed
```

### Order lifecycle

```text
              confirm                fulfill
  pending ──────────────► confirmed ────────────► fulfilled
     │                        │
     │ cancel                 │ cancel
     ▼                        ▼
  cancelled                cancelled

  customer:  pending → cancelled
  admin:     pending → confirmed → fulfilled
             pending | confirmed → cancelled
```

All transitions go through the same conditional write (`UPDATE ... WHERE status = expected`), so a stale or invalid transition cannot win a race.

## Scope

In scope (phase one, happy path):

- `orders` and `order_items` tables.
- Checkout: convert the authenticated user's current cart into an order.
- Snapshot product slug/name, variant SKU/name/attributes, unit price, currency, and quantity.
- Clear the cart in the same transaction as order creation.
- List and read the caller's orders.
- Cancel a pending order.
- Admin list/read and a guarded status transition endpoint.
- Access tests and happy-path tests.

Out of scope (phase two and later):

- Payment capture, refunds, and provider webhooks.
- Inventory checks and reservations; oversell prevention.
- Tax, shipping, discounts, and multi-currency.
- Emails, notifications, and background jobs.
- Idempotency keys for checkout.
- Status history / audit trail and event publishing.
- Observability (structured logs, metrics, tracing).
- Order numbers beyond the UUID.
- Soft delete and retention policy.

## Lifecycle

```
              confirm                fulfill
  pending ──────────────► confirmed ────────────► fulfilled
     │                        │
     │ cancel                 │ cancel
     ▼                        ▼
  cancelled                cancelled
```

Transition table:

| From | To | Who |
| --- | --- | --- |
| `pending` | `cancelled` | Customer (own order) or admin |
| `pending` | `confirmed` | Admin |
| `confirmed` | `fulfilled` | Admin |
| `confirmed` | `cancelled` | Admin |

`fulfilled` and `cancelled` are terminal.

Rules:

- Transitions are validated in the service against a single `ALLOWED_TRANSITIONS` mapping.
- The write is conditional: `UPDATE orders SET status = :to WHERE id = :id AND status = :expected`. `rowcount == 0` means the order is missing or the current status no longer allows the change; return `404` for a missing/foreign order and `409` for a stale or invalid transition.
- Payment is **not** part of `status`. The future Transactions domain adds a separate `payment_status` axis so the lifecycle does not need to be redesigned.
- `cancelled_at` is set when moving to `cancelled`; other transitions only move `updated_at`.

## Data model

```sql
orders (
  id             uuid pk,
  user_id        uuid null references users(id) on delete set null,
  customer_email varchar(255) not null,
  status         varchar(20) not null,   -- ck_orders_status
  currency       varchar(3) not null,
  subtotal       numeric(12,2) not null,
  total          numeric(12,2) not null,
  created_at     timestamptz not null,
  updated_at     timestamptz not null,
  cancelled_at   timestamptz null,
  check (subtotal >= 0),
  check (total >= 0)
)

order_items (
  id            uuid pk,
  order_id      uuid not null references orders(id) on delete cascade,
  product_id    uuid null references products(id) on delete set null,
  variant_id    uuid null references product_variants(id) on delete set null,
  product_slug  varchar(255) not null,
  product_name  varchar(255) not null,
  variant_sku   varchar(64) not null,
  variant_name  varchar(255) not null,
  attributes    jsonb not null default '{}',
  unit_price    numeric(12,2) not null,
  quantity      int not null,
  created_at    timestamptz not null,
  check (unit_price >= 0),
  check (quantity > 0)
)

index ix_orders_user_id_created_at on orders (user_id, created_at)
```

Why this differs from `cart_items`:

- **Snapshots are mandatory.** The catalog admin hard-deletes products; a foreign key with `CASCADE` would erase order history and `RESTRICT` would block catalog maintenance. `SET NULL` plus snapshot columns keeps the order readable after the catalog row is gone.
- **`user_id` is nullable with `SET NULL`** and `customer_email` is snapshotted, so deleting an account does not destroy financial records.
- **No live joins in responses.** Order responses read only snapshot columns.
- **No unique `(order_id, variant_id)`.** The cart already guarantees one line per variant, and nullable variant FKs make the constraint awkward after deletes. The order copy is the place where duplicates would be caught if that invariant ever changed.
- **`total` equals `subtotal` in phase one.** Both columns exist so tax, shipping, and discounts can be added without changing the API shape.

`OrderStatus` uses the same non-native enum pattern as `ProductStatus` / `UserRole`, with `values_callable` so the database stores `pending`, not `PENDING`.

## Checkout flow

`POST /api/v1/orders` is the only entry point. The client sends no body; prices are never accepted from the client.

```
BEGIN
  1. SELECT cart ... FOR UPDATE          -- serializes checkouts per user
  2. load items -> variant -> product
  3. validate: non-empty, active products, single currency
  4. INSERT orders    (status=pending, snapshots, totals)
  5. INSERT order_items (product/variant/price snapshots)
  6. DELETE cart_items WHERE cart_id = ...
COMMIT
```

Rules:

- **One transaction, one commit, at the end.** Do not call `CartService.get_cart`; it may create a cart and commit mid-flow. Read through `CartRepository`.
- **Lock the cart row first.** Two concurrent checkouts for one user: the second waits on `FOR UPDATE`, then sees the cart already cleared and gets `409 "Cart is empty"`. This is the phase-one answer to a double-submitted checkout.
- **Failure rolls back the whole thing.** No order row and no lost cart lines.
- **Empty or missing cart -> `409`**, not `404`; there is nothing to check out.
- **Revalidate at checkout.** A line added earlier may now point at an archived product or a changed price. Any inactive product -> `409`. A cart whose lines do not share one currency -> `409`. The order snapshots the current price.
- **The cart row stays.** Only `cart_items` are deleted, so the next `GET /cart` returns the same empty cart.

Future seam: inventory reservation slots in between step 3 and step 4; payment session creation happens after commit. Neither should require changing the route.

## API surface

All customer routes require a bearer token and live under `/api/v1/orders`.

| Method | Path | Purpose | Success |
| --- | --- | --- | --- |
| `POST` | `/api/v1/orders` | Check out the current cart | `201` |
| `GET` | `/api/v1/orders` | List own orders, newest first, `limit`/`offset` | `200` |
| `GET` | `/api/v1/orders/{order_id}` | Own order detail with snapshot items | `200` |
| `POST` | `/api/v1/orders/{order_id}/cancel` | `pending -> cancelled` | `200` |

Admin routes require an admin token and live under `/api/v1/admin/orders`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/admin/orders` | All orders, optional `status` filter, `limit`/`offset` |
| `GET` | `/api/v1/admin/orders/{order_id}` | Any order detail |
| `POST` | `/api/v1/admin/orders/{order_id}/transition` | Body `{"status": "confirmed"}`; guarded by the state machine |

Status codes:

| Status | When |
| --- | --- |
| `401` | Missing or invalid token |
| `403` | Non-admin calls an admin route |
| `404` | Unknown order, or another user's order on a customer route |
| `409` | Empty cart, inactive product at checkout, mixed currency, or invalid/stale transition |
| `422` | Invalid payload, for example an unknown target status |

Returning `404` for another user's order avoids leaking its existence.

## Response shape

```json
{
  "id": "0f2c1d5e-2a3b-4c5d-8e9f-1a2b3c4d5e6f",
  "status": "pending",
  "currency": "USD",
  "subtotal": "39.98",
  "total": "39.98",
  "created_at": "2026-11-25T12:00:00Z",
  "cancelled_at": null,
  "items": [
    {
      "id": "7f6e5d4c-3b2a-4190-8877-665544332211",
      "product_slug": "classic-tee",
      "product_name": "Classic Tee",
      "variant_sku": "TEE-BLK-S",
      "variant_name": "Black / Small",
      "attributes": {"color": "black", "size": "S"},
      "unit_price": "19.99",
      "quantity": 2,
      "line_total": "39.98"
    }
  ]
}
```

List responses use the catalog-style envelope:

```json
{
  "items": ["..."],
  "total": 3,
  "limit": 20,
  "offset": 0
}
```

Notes:

- `unit_price` and `attributes` come from the order item snapshot, not from the live catalog.
- `line_total` is computed as `unit_price * quantity`.
- `subtotal` is the sum of line totals; `total` equals `subtotal` in phase one.
- Orders are ordered newest first for both list endpoints.

## Business rules

- Checkout is cart-based only; there is no direct "create order with arbitrary lines" route.
- The client never sends prices, totals, or currency.
- An order starts as `pending`.
- Only the owning customer can read or cancel their order.
- Customers can cancel only while `pending`; admins can cancel `pending` or `confirmed`.
- Prices and names are immutable after checkout, even if the catalog changes.
- Deleting a product, variant, or user does not delete the order or lose its snapshots.
- Deleting an order is not exposed; `DELETE` is deferred.
- Totals and state transitions are calculated/validated in `OrderService`, not on ORM models.

## Implementation notes (planned)

- `OrderRepository` mirrors `CartRepository`: it flushes, the service commits, and bulk writes report success through `rowcount`.
- `CartRepository.get_cart_for_update` is a new read used only by checkout; it applies `with_for_update()` to the `carts` row.
- `CartRepository.clear_items` is a bulk `DELETE`, called inside the checkout transaction.
- `OrderService.checkout` loads the cart, validates, inserts the order and items, clears the cart, then commits once.
- `OrderService.transition` uses the conditional `UPDATE ... WHERE status = expected` pattern.
- `order_to_response` reads snapshots only, so it cannot trigger catalog joins.
- Existing clients of the cart see no change; checkout is additive.

## Tests (planned)

`tests/test_order_mvp.py`:

- `401` on all customer and admin routes without a token.
- Empty cart checkout returns `409` and creates no order.
- Happy-path checkout returns `201`, `pending`, correct totals, and an empty cart afterwards.
- Snapshot isolation: change the price or archive the product after checkout, then read the order.
- Deleting a product after checkout keeps the order readable.
- A mixed-currency cart is rejected.
- A cart line whose product became inactive is rejected.
- Two users get isolated orders and cannot read or cancel each other's.
- List pagination and newest-first ordering.
- Unknown order id returns `404`.
- Cancel `pending` succeeds; a repeat cancel or cancelling `fulfilled` returns `409`.
- Admin `pending -> confirmed -> fulfilled` succeeds.
- Admin `pending -> fulfilled` returns `409`.
- A customer calling an admin route gets `403`.
- Database constraints reject `quantity <= 0` and negative totals.

Race coverage (two sessions plus a barrier) is tracked in [`testing-waitlist.md`](testing-waitlist.md).

## Tasks

- [ ] Add `Order` and `OrderItem` models with status enum, constraints, and index.
- [ ] Add the Alembic migration and import the model in `migrations/env.py`.
- [ ] Add `OrderResponse`, `OrderItemResponse`, `OrderListResponse`, and `OrderTransition` schemas.
- [ ] Add `OrderRepository` with create, read, list, and conditional transition.
- [ ] Add `CartRepository.get_cart_for_update` and `clear_items`.
- [ ] Add `OrderService` with checkout, read/list, cancel, and transition.
- [ ] Add customer routes and mount them in `app/main.py`.
- [ ] Add admin routes behind `require_admin`.
- [ ] Add `tests/test_order_mvp.py` and update the conftest truncate list.
- [ ] Update `docs/testing.md`, `docs/testing-waitlist.md`, `docs/sessions-and-concurrency.md`, `README.md`, and `docs/manual-test-data.md`.

## Decisions settled

- Snapshot catalog and pricing data at checkout; never read live prices for an order.
- `SET NULL` FKs plus snapshots for product, variant, and user.
- Order lifecycle: `pending -> confirmed -> fulfilled`, with `cancelled` reachable from `pending` and `confirmed`.
- Payment stays a separate axis and is deferred.
- Checkout takes no body and always starts from the current cart.
- Customer cancel is limited to `pending`.
- `SELECT ... FOR UPDATE` on the cart row is part of phase one.
- Order addressed by UUID; a human-readable order number is deferred.
- Admin lifecycle endpoints are part of phase one so the state machine has a driver.

## Deferred

- Payment capture, refunds, webhooks, and `payment_status`.
- Inventory reservation and availability checks.
- Tax, shipping, discounts, and multi-currency.
- `Idempotency-Key` support for checkout.
- Status history / audit trail and an outbox for order events.
- Order number generation.
- Order deletion, soft delete, and retention policy.
- Notifications and background jobs.
- Structured logging, metrics, and tracing.
- Pagination meta beyond `total`/`limit`/`offset`.

## Dependencies

- Auth: `get_current_user` for ownership and `require_admin` for admin routes.
- Cart: `Cart`, `CartItem`, and `CartRepository` for reading and clearing at checkout.
- Catalog: `Product`/`ProductVariant` for snapshots and active-status validation.
- Inventory: not required in phase one; reservation is inserted at checkout later.
- Transactions: not required in phase one; payment moves `payment_status`, not `OrderStatus`.
