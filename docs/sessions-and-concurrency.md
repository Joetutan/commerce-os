# Sessions and Concurrency

How Commerce-OS uses SQLAlchemy sessions, where transaction boundaries live, and which concurrency problems the current design does and does not handle.

Scope: current code (`app/configs/db_connection.py`, repositories, services, cart phase one). The goal is a mental model, not an exhaustive SQLAlchemy manual.

---

## 1. The pieces

```text
process
├── get_engine()            cached, one Engine + connection pool
├── get_session_factory()   cached, one sessionmaker bound to that engine
└── request
    ├── get_db()            new Session, closed at teardown
    ├── repository          takes the Session
    └── service             owns business rules and commit/rollback
```

`app/configs/db_connection.py`:

```python
@cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
```

| Setting | Why |
| --- | --- |
| `@cache` on engine/factory | One pool per process. Creating an engine per request leaks connections. |
| `pool_pre_ping=True` | Discard a pooled connection that died (DB restart, idle timeout) instead of failing the request. |
| `autoflush=False` | Queries never push half-built writes to the database. Writes happen only at an explicit `flush()` or `commit()`. |
| `expire_on_commit=False` | After a service commits, it can still read the object to build the response. No surprise `SELECT` and no detached-instance errors. |
| `get_db()` closes in `finally` | The connection returns to the pool even when the route raises. |

`get_db` is a FastAPI dependency. Within one request, the result is cached, so `get_current_user` and the route's service receive **the same** `Session` even though both declare `Depends(get_db)`.

A session is request-scoped. Never pass it to a background task, another thread, or a websocket that outlives the request.

The pool is **per process**. With multiple uvicorn workers or pods, each process has its own pool. Nothing in the code sets pool size, so SQLAlchemy defaults apply.

---

## 2. A request end to end

```text
GET /api/v1/cart
  │
  ├─ Depends(get_db)             Session created
  ├─ Depends(get_current_user)   reuses that Session, SELECT users
  ├─ CartService.get_cart()
  │    ├─ SELECT cart + items + variant + product
  │    └─ maybe INSERT cart, then COMMIT
  └─ response built from ORM objects
  │
  └─ teardown: Session.close() → connection back to pool
```

Two things worth noticing:

- The auth lookup and the cart lookup share one session and one transaction (unless something commits in between).
- `GET /cart` creates a cart on first call. `GET` is idempotent in effect (repeat calls converge on the same cart) but not **safe**, because it writes.

---

## 3. Transaction boundaries

SQLAlchemy starts a transaction implicitly on the first SQL statement. `commit()` flushes pending changes and ends the transaction; `rollback()` discards and ends it.

The project rule:

- **Repository**: `add`, `flush`, `delete`. `flush()` sends SQL and surfaces constraint errors, but does not end the transaction.
- **Service**: decide, then `commit()`; on error, `rollback()` and translate the exception.
- **Route**: thin. No commits.

```python
# repository: make the write visible, do not commit
def create_cart(self, user_id: UUID) -> Cart:
    cart = Cart(user_id=user_id)
    self.db.add(cart)
    self.db.flush()
    return cart


# service: business check, then the transaction boundary
def create_cart(self, user_id: UUID) -> Cart:
    try:
        cart = self.repository.create_cart(user_id=user_id)
        self.repository.commit()
        return cart
    except IntegrityError:
        self.repository.rollback()
        ...
```

A single request can contain **more than one** transaction. The cart get-or-create commits first; the add-item commit comes after. Another request can interleave between them. The design tolerates that because the database constraints hold the invariants (one cart per user, one line per variant).

`autoflush=False` means `commit()` is still a flush point, and `flush()` is explicit. It does **not** mean writes are deferred until commit if you call `flush()` yourself.

---

## 4. The identity map and "no expiry"

Within one session, a row maps to exactly one Python object:

```python
a = session.scalar(select(Cart).where(Cart.id == cart_id))
b = session.scalar(select(Cart).where(Cart.id == cart_id))
assert a is b  # identity map
```

Because `expire_on_commit=False`, after `commit()` the object keeps its loaded attributes:

```python
cart = service.get_cart(user_id)
service.repository.commit()
cart.id  # still available, no reload
cart.items  # still the collection loaded before the commit
```

That is convenient for building responses, but it has a sharp edge:

```python
cart = repository.get_cart_by_user(user_id)  # cart.items loaded: []
repository.add_item(cart_id=cart.id, variant_id=variant.id, quantity=1)
repository.commit()
len(cart.items)  # 0 — the collection was loaded before the insert
```

Inserting a row by foreign key does not patch an already-loaded collection. Options:

1. Insert through the relationship: `cart.items.append(item)`.
2. Re-query with `.execution_options(populate_existing=True)`.
3. `session.expire_all()` before reading again.

`rollback()` is different: it always expires objects in the session. After a rollback, the next attribute access reloads from the database.

Core statements do not go through the ORM's attribute tracking:

```python
update(CartItem).where(...).values(quantity=CartItem.quantity + 1)
```

The row changes, but a `CartItem` already loaded in the session may still hold the old value. SQLAlchemy's `synchronize_session` (enabled by default for `Session.execute`) tries to keep loaded objects in sync; a `populate_existing` re-query makes it deterministic.

---

## 5. Concurrency fundamentals

Two requests use two sessions, two connections, and two transactions. They can run in parallel:

- FastAPI runs `def` endpoints in a threadpool, so one process still serves routes concurrently.
- Multiple workers or pods add more parallelism.
- A single cart per user does **not** serialize requests. It only guarantees one cart row.

The three properties that get confused:

| Property | Question | Example |
| --- | --- | --- |
| Atomicity | Is the change all-or-nothing? | `UPDATE ... SET quantity = quantity + 1` is one indivisible statement |
| Isolation | Can concurrent transactions see each other's half-done work? | Postgres default `READ COMMITTED`: each statement sees the latest committed data |
| Idempotency | Does replaying the same request change the outcome? | `SET quantity = 3` is idempotent; `quantity = quantity + 3` is not |

### Postgres behaviors to rely on

- **Unique index**: an insert that conflicts with an uncommitted row **blocks** until that transaction ends. If it commits, the insert raises a unique violation. If it rolls back, the insert succeeds.
- **`UPDATE` row lock**: the first update locks the row until commit. A second update waits, then applies its expression to the committed value.
- **`READ COMMITTED`**: a `SELECT` does not lock. A later `UPDATE` in the same transaction can still overwrite a value another transaction committed in between.

---

## 6. Where cart operations overlap

### 6.1 First cart request for a user

Two requests both find no cart and both insert.

```text
unique (user_id) protects the row

A: SELECT cart → none
B: SELECT cart → none
A: INSERT cart, COMMIT
B: INSERT cart → IntegrityError
B: rollback, SELECT cart → A's cart
```

Handled by `unique(user_id)` plus the retry in `create_cart`. The result is one cart, no error.

### 6.2 Two adds for a variant that is not in the cart

```text
unique (cart_id, variant_id) protects the row

A: SELECT item → none
B: SELECT item → none
A: INSERT item(quantity=1), COMMIT
B: INSERT item → IntegrityError
B: rollback, SELECT item → A's row
B: quantity = quantity + 1  → 2
```

Handled by `unique(cart_id, variant_id)` plus the `IntegrityError` retry. Without the retry, the loser gets a `500` or a misleading `409`.

### 6.3 Two adds for a variant that is already in the cart

There is no unique violation here, because no insert happens.

```text
start quantity = 2

A: SELECT → 2
B: SELECT → 2
A: UPDATE SET quantity = 3   (Python computed 2 + 1)
B: UPDATE SET quantity = 3   (Python computed 2 + 1)
final = 3                    should be 4
```

This is a **lost update**. Silent, no error, no log. The unique constraint cannot help.

The fix is an atomic delta, not a lock:

```python
# ORM assignment: value computed in Python → lost update
item.quantity += data.quantity

# SQL expression: value computed by the database → atomic
update(CartItem).where(...).values(quantity=CartItem.quantity + data.quantity)
```

With the SQL expression, the second `UPDATE` waits for the row lock and recomputes against the committed value:

```text
A: UPDATE quantity = quantity + 1 → 3, lock held
B: UPDATE quantity = quantity + 1 → waits
   A commits
   B recomputes on 3 → 4
```

`CartRepository.increment_item` uses the SQL-expression form, so the cart no longer has this lost-update window.

### 6.4 Quantity cap

Checking the cap in Python has the same race:

```python
if item.quantity + add > 99:  # both requests pass at 98
    raise ...
item.quantity += add
```

Put the limit in the statement that writes:

```sql
UPDATE cart_items
SET quantity = quantity + 2
WHERE cart_id = ... AND variant_id = ... AND quantity + 2 <= 99;
```

`rowcount == 0` then means either "no such line" or "cap exceeded", which the caller distinguishes.

### 6.5 Idempotency of retries

| Operation | SQL | Replay |
| --- | --- | --- |
| Add to cart (delta) | `quantity = quantity + q` | adds again |
| Set quantity (absolute) | `quantity = q` | same result |

`POST /cart/items` is a delta by design ("add 2 more"), so a retried request double-adds. That is acceptable for phase one; idempotency keys belong with Orders, where a duplicate means a duplicate charge. `PATCH /cart/items/{item_id}` uses an absolute quantity and is naturally idempotent.

---

## 7. Decisions and why

| Decision | Why |
| --- | --- |
| Session per request, closed in `finally` | No cross-request state, no leaked connections. |
| `autoflush=False` | Explicit writes; a read endpoint cannot accidentally flush a partial object graph. |
| `expire_on_commit=False` | Services can commit and then build a response without extra queries. |
| Repository flushes, service commits | Constraint errors surface inside the service's `try`, where they can be translated to HTTP errors. |
| Lazy cart creation | Registration stays an auth concern; existing users get carts; guests remain possible later. |
| `unique(user_id)` + retry | The database guarantees one cart even when two first requests race. |
| `unique(cart_id, variant_id)` | One line per variant per cart; also provides the conflict target for a future upsert. |
| Insert-first, retry as increment | Readable happy path; the rare race is explicit in the `except`. |
| Totals computed at read time | No denormalized price or total columns to go stale; catalog is the source of truth. |
| Single-currency assumption | Phase one is single-currency: currency is snapshotted from the catalog, never converted, and mixed carts are rejected at checkout. Multi-currency is deferred. |
| `GET /cart` may create | Simpler than a nullable cart id; idempotent in effect, but not a "safe" HTTP method. |
| `POST` is a delta, `PATCH` is absolute | Matches user intent: "add two more" versus "make it two". `PATCH` is replay-safe; `POST` is not. |
| Bulk `DELETE` + `rowcount` | One statement, no fetch, and `rowcount == 0` maps cleanly to `404`. |
| Mutations return the full cart | The client never needs a follow-up `GET`, and the response is computed from committed state. |

---

## 8. Deliberately deferred

| Not doing yet | When it matters |
| --- | --- |
| `SELECT ... FOR UPDATE` on the cart | If increments must be strictly serialized rather than atomic per row. |
| `ON CONFLICT DO UPDATE` upsert | If the insert/retry branch becomes noisy, or for reservations. |
| `Idempotency-Key` storage | Orders/checkout, where retries must not duplicate side effects. |
| `SERIALIZABLE` isolation | Only for multi-row invariants that constraints cannot express. |
| Multi-currency carts | When catalog and checkout support more than one currency. |
| Inventory reservations | Checkout, not cart. |

---

## 9. Practical checklist

When adding a route or a repository method:

1. Do not create or share sessions inside services. Take the one `get_db` provides.
2. Commit in the service, not the route.
3. Call `flush()` in the repository when you need the generated id or want a constraint error before commit.
4. On `IntegrityError`, `rollback()` first; the session is unusable until you do.
5. If you insert a child by foreign key, either append through the relationship or re-query with `populate_existing=True`.
6. For counters and balances, write SQL expressions (`quantity = quantity + q`), not Python `+=`.
7. Put limit and status conditions in the same `WHERE` as the write.
8. Return the full cart from mutations so the client never needs a follow-up read.
9. For every mutation, ask: if the client retries this, is the outcome still correct?

---

## 10. Testing notes

- API tests use `TestClient`, which runs the real `get_db`; `tests/conftest.py` truncates tables before each test.
- `db_session` creates a separate `Session` for direct assertions. It uses its own connection, so it only sees committed state.
- The truncate list is explicit: `cart_items, carts, product_variants, products, users`, with `RESTART IDENTITY CASCADE`.
- Cart coverage lives in `tests/test_cart_mvp.py` (16 tests). It exercises the delta/absolute split at the API level:

```python
# delta: two calls add twice
client.post("/api/v1/cart/items", json={"variant_id": v, "quantity": 1})
client.post("/api/v1/cart/items", json={"variant_id": v, "quantity": 1})
assert get_quantity() == 2

# absolute: two calls converge
client.patch(f"/api/v1/cart/items/{item_id}", json={"quantity": 3})
client.patch(f"/api/v1/cart/items/{item_id}", json={"quantity": 3})
assert get_quantity() == 3
```

Reproducing the true interleaved race needs two sessions/threads and a barrier between `SELECT` and `INSERT`. That is worth doing once, not on every test.

---

## 11. Known gaps

- No test drives two concurrent requests through both branches. The insert/retry and increment paths are covered individually through the API, but not the interleaved race.
- The `IntegrityError` catch in `add_item` is broad. A foreign-key failure (for example, the variant disappearing between the active check and the insert) would fall through to `increment_item` and surface as `409 "Quantity limit exceeded"`.
- `Cart.updated_at` does not move when only `cart_items` change; item mutations do not touch the parent row.
- `cart_id` carries an index that duplicates the leading column of `unique(cart_id, variant_id)`. Harmless, but a future migration could drop it.
- Multi-currency is unsupported by decision: the order snapshots the catalog currency, no conversion is performed, and checkout rejects a mixed cart. Deferred.
- The cart has no whole-cart clear endpoint (`DELETE /api/v1/cart`); clients remove lines one at a time.
- Migration for carts exists (`ebc621a337d9`); `alembic check` is clean because `migrations/env.py` imports the cart model.

---

## 12. One-paragraph summary

Each request gets its own session and transaction; services commit, repositories flush. `expire_on_commit=False` keeps objects readable after commit but means loaded collections can go stale, so either mutate through relationships or re-query with `populate_existing`. Concurrent requests are independent transactions, so the database constraints (`unique(user_id)`, `unique(cart_id, variant_id)`, `quantity > 0`) are the only real guarantees; application-level `if` checks can race. Use retries for insert races, SQL expressions for counter updates, conditions in the same `WHERE` for caps, and keep delta semantics (non-idempotent) separate from absolute set semantics (idempotent).
