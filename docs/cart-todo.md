# Cart Todo

Phase one is implemented: one persistent cart per user, backed by Postgres, priced live from the catalog.

Cart is pre-checkout intent. It does not reserve stock, and it does not integrate with Inventory or Orders yet.

## Status

| Piece | State |
| --- | --- |
| `Cart` / `CartItem` models | Done |
| Alembic migration `ebc621a337d9` | Done |
| Request/response schemas | Done |
| `CartRepository` | Done |
| `CartService` | Done |
| Routes mounted in `app/main.py` | Done |
| Happy-path tests (`tests/test_cart_mvp.py`, 16) | Done |
| Docs | Done |

See [`sessions-and-concurrency.md`](sessions-and-concurrency.md) for the session, transaction, and race reasoning behind the implementation.

## Scope

In scope:

- `carts` and `cart_items` tables.
- One active cart per user.
- Read cart, add item, change quantity, remove item.
- Live pricing and totals from `product_variants`.
- Authenticated routes using `get_current_user`.
- Happy-path and access tests.

Out of scope:

- Guest carts and merge-on-login.
- Multiple carts, saved carts, and wishlists.
- Price snapshots and price-change notices.
- Inventory availability checks and reservations.
- Checkout and cart-to-order conversion.
- Redis or client-side cart storage.
- Idempotency keys for retried `POST` requests.

## Data model

```sql
carts (
  id uuid pk,
  user_id uuid not null unique references users(id) on delete cascade,
  created_at timestamptz not null,
  updated_at timestamptz not null
)

cart_items (
  id uuid pk,
  cart_id uuid not null references carts(id) on delete cascade,
  variant_id uuid not null references product_variants(id) on delete cascade,
  quantity int not null check (quantity > 0),
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique (cart_id, variant_id)
)
```

Rules:

- One cart per user; `unique(user_id)`.
- The same variant added twice increments quantity instead of creating a second row; `unique(cart_id, variant_id)` is the conflict target.
- The cart is created lazily on the first `GET`, `POST`, or `PATCH`; `DELETE` never creates one.
- Do not store unit price, line total, or cart total; compute them from the catalog.
- Store `variant_id`, never `product_id`; the product is reached through the variant.
- `cart_id` and `variant_id` cascade on delete.

## API surface

All routes require a bearer token and live under `/api/v1/cart`.

| Method | Path | Purpose | Success |
| --- | --- | --- | --- |
| `GET` | `/api/v1/cart` | Current cart with items, live prices, and totals | `200` |
| `POST` | `/api/v1/cart/items` | Add a variant, or increment its quantity | `200` |
| `PATCH` | `/api/v1/cart/items/{item_id}` | Set an absolute quantity | `200` |
| `DELETE` | `/api/v1/cart/items/{item_id}` | Remove a line | `204` |

Status codes:

| Status | When |
| --- | --- |
| `401` | Missing or invalid token |
| `404` | Variant not found, cart not found, or item not found |
| `409` | Line quantity would exceed `99` |
| `422` | Invalid `quantity` or payload |

`PATCH` sets an absolute quantity in `1..99` and is idempotent. Use `DELETE` to remove a line; `quantity: 0` is rejected with `422`.

`DELETE` returns `404` when the item does not exist, so a repeated delete is not silently accepted.

## Response shape

Mutations return the full cart, so the client never needs a follow-up `GET`.

```json
{
  "id": "0f2c1d5e-2a3b-4c5d-8e9f-1a2b3c4d5e6f",
  "items": [
    {
      "id": "7f6e5d4c-3b2a-4190-8877-665544332211",
      "quantity": 2,
      "line_total": "39.98",
      "variant": {
        "id": "9a8b7c6d-5e4f-4321-9876-543210fedcba",
        "sku": "TEE-BLK-S",
        "name": "Black / Small",
        "price": "19.99",
        "currency": "USD",
        "attributes": {"color": "black", "size": "S"},
        "product": {
          "id": "1b2c3d4e-5f60-4718-9a2b-3c4d5e6f7081",
          "slug": "classic-tee",
          "name": "Classic Tee"
        }
      }
    }
  ],
  "total_quantity": 2,
  "subtotal": "39.98",
  "currency": "USD"
}
```

Empty cart:

```json
{
  "id": "0f2c1d5e-2a3b-4c5d-8e9f-1a2b3c4d5e6f",
  "items": [],
  "total_quantity": 0,
  "subtotal": "0.00",
  "currency": null
}
```

Notes:

- `price`, `line_total`, and `subtotal` are computed at read time from `product_variants`.
- `variant.attributes` is variant data; `variant.product` supplies only `id`, `slug`, and `name`.
- `total_quantity` is the sum of quantities, not the number of lines.
- `currency` is `null` on an empty cart and the first line's currency otherwise.

## Business rules

- The client sends only `variant_id` and `quantity`; never prices or totals.
- `POST` adds to an existing line (`quantity += request`) and is therefore not idempotent. `PATCH` is an absolute set and is idempotent.
- A line cannot exceed `99` units; the cap is enforced inside the atomic `UPDATE ... WHERE quantity + n <= 99`.
- Only variants whose product is `active` can be added. Draft and archived products return `404`.
- Existing lines remain visible if a product is later archived; they can still be updated or removed.
- Phase one assumes a single global currency. The cart derives `currency` from the first line and does not convert. Multi-currency is deferred.
- Totals are calculated in `CartService`, not on the ORM models.

## Implementation notes

- `CartRepository.get_cart_by_user` eager-loads items → variant → product and uses `populate_existing=True`, so a response built after a Core update is not stale.
- `CartRepository.increment_item` is an atomic SQL delta: `SET quantity = quantity + n WHERE ... AND quantity + n <= 99`.
- `CartRepository.set_item_quantity` is an absolute `SET quantity = n`, scoped by `cart_id` and `item_id`.
- `CartRepository.delete_item` is a bulk `DELETE` and reports matching rows via `rowcount`.
- `CartService.add_item` inserts first; on the unique-pair race it rolls back and retries as an atomic increment.
- `CartService.create_cart` handles the `unique(user_id)` race by re-reading the winning cart.

## Tests

`tests/test_cart_mvp.py` covers:

- `401` on all routes without a token.
- Empty cart creation, stable cart id, and one row per user.
- Add, increment, multiple lines, live prices, totals, and single currency.
- Unknown variant, draft-product variant, and schema/cap bounds.
- Absolute `PATCH`, idempotent repeat, missing item, and missing cart.
- `DELETE`, totals after removal, repeated delete, and missing cart.
- Cross-user isolation for update and delete.

See [`testing.md`](testing.md) for the suite details.

## Tasks

- [x] Add `Cart` and `CartItem` models.
- [x] Add the Alembic migration.
- [x] Add request/response schemas, including computed totals.
- [x] Add `CartRepository` with cart lookup, item lookup, increment, set, delete, and insert.
- [x] Add `CartService` with ownership, quantity, and currency rules.
- [x] Add the routes and mount the router in `app/main.py`.
- [x] Add happy-path tests: read empty cart, add item, increment, set quantity, delete, `401` without a token.
- [x] Document the routes in `docs/testing.md` and this file.

## Decisions settled

- Single currency per cart in phase one; multi-currency later.
- Create the cart lazily on the first request.
- Maximum quantity per line is `99`.
- Only active-product variants are addable; existing archived lines stay visible.
- `PATCH` uses an absolute quantity and does not remove lines; `DELETE` removes.
- Items are addressed by `item_id` in the URL.

## Outstanding features

### Clear cart (`DELETE /api/v1/cart`)

Phase one has no whole-cart clear; clients remove lines one at a time with `DELETE /api/v1/cart/items/{item_id}`.

Proposed contract:

| Item | Value |
| --- | --- |
| Method and path | `DELETE /api/v1/cart` |
| Auth | Bearer token; same `get_current_user` dependency |
| Effect | Delete every `cart_items` row for the user's cart; keep the `carts` row |
| Success | `204 No Content` |
| No cart | Decide between `204` (idempotent no-op) and `404 "Cart not found"` (matches per-item `DELETE`) |
| Side effects | Never creates a cart; totals become empty on the next `GET` |

Implementation sketch:

- Add `CartRepository.clear_items(cart_id)` as a bulk `delete(CartItem).where(CartItem.cart_id == cart_id)` returning `rowcount > 0`.
- Add `CartService.clear_cart(user_id)` that reads the cart without creating it, returns `False`/`404` per the chosen no-cart rule, and commits.
- Add the route returning `status.HTTP_204_NO_CONTENT`.
- Tests: `401` without a token; `204` with lines and an empty cart afterwards; repeat call behavior; another user's cart untouched.

## Deferred

- Guest carts and merge-on-login.
- Multiple or saved carts.
- Price snapshots and price-change notices.
- Inventory checks and reservations.
- Cart-to-order conversion.
- `Idempotency-Key` support for retried `POST` requests.
- Multi-currency and conversion.
- Atomic upsert (`ON CONFLICT DO UPDATE`) replacing the insert/retry branch.

## Dependencies

- Catalog: `ProductVariant` for price, currency, and attributes; `Product` for status and name/slug.
- Auth: `get_current_user` for ownership.
- Inventory: not required for phase one; availability checks are added at checkout later.
- Orders: cart-to-order conversion is a later phase.
