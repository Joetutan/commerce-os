# Testing Waitlist

Tests to explore after the current MVP suites. The active suites are documented in [`testing.md`](testing.md).

## Infrastructure

- [ ] Add `unit` and `integration` pytest markers.
- [ ] Run unit tests without a database: `pytest -m unit`.
- [x] Add Postgres as a CI service container.
- [ ] Run `alembic check` in CI (the suite already applies migrations).
- [ ] Add coverage reporting (`pytest-cov`) and a minimum threshold.
- [ ] Replace per-test truncation with transaction rollback if the suite grows.
- [ ] Add factories for users and tokens.
- [ ] Add `freezegun` or a clock fixture for expiry tests.
- [ ] Add a test that `get_db` closes its session.

## Schema and model

- [ ] `UserCreate` rejects missing username, email, and password.
- [ ] `UserCreate` rejects emails without `@`.
- [ ] `UserCreate` accepts subdomains and plus addressing.
- [ ] `UserCreate` ignores an extra `role` field.
- [ ] `UserResponse` omits `password_hash`.
- [ ] `UserResponse` serializes `id` as a UUID string.
- [ ] `UserResponse.model_validate(user)` works via `from_attributes`.
- [ ] `User.id` is a `uuid.UUID`.
- [ ] `User.created_at` is populated.
- [ ] Raw insert with `role='invalid'` violates `ck_users_role`.
- [ ] Duplicate username behavior is documented or constrained.
- [ ] Role values are stored lowercase (`customer`, not `CUSTOMER`).

## Security unit tests

- [ ] `hash_password` returns a value different from the plaintext.
- [ ] Hash uses Argon2.
- [ ] `verify_password` returns `True` for the correct password.
- [ ] `verify_password` returns `False` for the wrong password.
- [ ] Malformed hash handling is defined.
- [ ] `create_access_token` includes a string `sub`.
- [ ] `exp` matches the configured expiry window.
- [ ] Token uses the configured algorithm and secret.
- [ ] `verify_access_token` rejects expired tokens.
- [ ] Rejects malformed tokens.
- [ ] Rejects wrong-secret tokens.
- [ ] Rejects wrong-algorithm tokens.
- [ ] Rejects missing `sub`.
- [ ] Rejects non-string `sub`.
- [ ] Rejects empty tokens.
- [ ] `security()` returns a cached instance.

## Repository

- [ ] `create` inserts and refreshes a user.
- [ ] `create` stores the provided hash, not plaintext.
- [ ] `create` applies the default role.
- [ ] `get_by_email` returns a matching user.
- [ ] `get_by_email` returns `None` for unknown emails.
- [ ] Email lookup is case-sensitive (or normalize and test).
- [ ] `get_by_id` returns a matching user.
- [ ] `get_by_id` returns `None` for unknown UUIDs.
- [ ] Rollback leaves no partial user.

## Service unit tests

- [ ] `register` raises `409` for an existing email.
- [ ] `register` does not hash or create when the email exists.
- [ ] `register` hashes the password before `create`.
- [ ] `create` never receives plaintext.
- [ ] `register` returns the created user.
- [ ] `IntegrityError` from `create` maps to `409` (currently unhandled).
- [ ] `login` raises `401` for unknown email.
- [ ] `login` raises `401` for wrong password.
- [ ] Both login failures return the same body.
- [ ] `login` passes `user.id` to token creation.
- [ ] `get_user` returns `None` for unknown email.
- [ ] `get_user` return type becomes `User | None`.

## Dependency tests

- [ ] Valid token plus existing user returns the user.
- [ ] Repository receives a `UUID`, not a string.
- [ ] Malformed token returns `401`.
- [ ] Expired token returns `401`.
- [ ] Wrong-secret token returns `401`.
- [ ] Missing `sub` returns `401`.
- [ ] Non-UUID `sub` returns `401` before the repository call.
- [ ] Deleted user returns `401`.
- [ ] `401` includes `WWW-Authenticate: Bearer`.
- [ ] Repository is not called when token validation fails.

## API negative cases

- [ ] Register with missing username/password returns `422`.
- [ ] Register with form data instead of JSON returns `422`.
- [ ] Register with `role: "admin"` still creates a customer.
- [ ] Login with JSON instead of form data returns `422`.
- [ ] Login with missing form fields returns `422`.
- [ ] `/me` without an `Authorization` header returns `401`.
- [ ] `/me` with a token for a deleted user returns `401`.
- [ ] `/me` with a wrong-secret token returns `401`.

## Cart

Coverage gaps left after `tests/test_cart_mvp.py` (16 tests).

- [ ] Two concurrent `POST`s for a new variant: one inserts, the other retries as an increment; both survive.
- [ ] Two concurrent `POST`s for an existing line: atomic `quantity = quantity + n` yields the summed total.
- [ ] Two concurrent first requests create one cart, not two.
- [ ] Cap race: two adds that each fit under `99` alone but not together; exactly one succeeds and the line never exceeds `99`.
- [ ] `IntegrityError` on `insert_item` from a foreign-key failure (variant deleted mid-request) does not surface as `409 "Quantity limit exceeded"`.
- [ ] `POST` with an idempotency key replays safely (deferred until checkout).
- [ ] Multi-currency is out of scope: a mixed-currency cart is rejected at checkout rather than converted.
- [ ] A line whose product is archived after being added stays visible and removable.
- [ ] A line whose variant is deleted by the catalog admin disappears or raises a defined error.
- [ ] Raw insert with `quantity = 0` violates `ck_cart_items_quantity`.
- [ ] Duplicate `(cart_id, variant_id)` violates `uq_cart_items_cart_id_variant_id`.
- [ ] Duplicate `user_id` in `carts` violates the unique constraint.
- [ ] Deleting a user cascades to their cart and cart items.
- [ ] Deleting a product or variant cascades to cart items.
- [ ] `DELETE /api/v1/cart` clears all lines in one call (endpoint does not exist yet).
- [ ] `Cart.updated_at` reflects item mutations (currently it does not).
- [ ] `PUT`/`PATCH` on `/api/v1/cart` root is rejected or defined.
- [ ] Cart response exposes no more product fields than `id`, `slug`, and `name`.
- [ ] Response currency is `null` exactly when the cart is empty.

## Orders

Phase one is planned in [`orders-todo.md`](orders-todo.md); no order tests exist yet.

- [ ] Two concurrent checkouts for one user: `FOR UPDATE` yields exactly one order; the other gets `409 "Cart is empty"`.
- [ ] An item added while checkout is running is either ordered or left in the cart, never silently deleted.
- [ ] Checkout clears the cart in the same transaction; a failed insert leaves the cart intact.
- [ ] `Idempotency-Key` replay does not create a second order (deferred).
- [ ] A mixed-currency cart is rejected with `409`; no conversion is attempted.
- [ ] A line whose product was archived after being added is rejected at checkout.
- [ ] Snapshot immutability: changing the catalog price or name after checkout does not change the order.
- [ ] Deleting a product, variant, or user leaves the order readable (`SET NULL` plus snapshots).
- [ ] Concurrent transitions: two admins cannot both move the same order out of a state.
- [ ] A customer cannot read or cancel another user's order.
- [ ] Invalid transitions return `409`; customer cancel is limited to `pending`.
- [ ] Raw insert with `quantity <= 0` or negative totals violates the order checks.

## End-to-end and security

- [ ] Register, login, and `/me` for a second user.
- [ ] Confirm no cross-user data leakage.
- [ ] Password and hash never appear in responses.
- [ ] Tokens cannot be forged with another secret.
- [ ] Tokens cannot use an unexpected algorithm.
- [ ] Admin-only routes return `403` for customers.
- [x] Admin routes allow admins.
- [ ] Public registration cannot create an admin.
- [ ] Rate limiting is evaluated as an integration concern.

## Known gaps to address before some tests can pass

- [ ] `username` has no unique constraint or duplicate check.
- [ ] Login `401` responses lack `WWW-Authenticate`.
- [ ] `AuthService.get_user` is annotated `-> User` but returns `User | None`.
- [ ] `AuthService` raises `HTTPException` directly.
- [ ] No password policy (`min_length`, complexity).
- [ ] No `IntegrityError` handling on registration.
- [x] Admin authorization dependency exists (`require_admin`).
- [ ] No admin negative-case tests (`401`/`403`) outside the happy-path suite.
- [ ] No rate limiting.
