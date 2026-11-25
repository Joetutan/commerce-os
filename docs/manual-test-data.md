# Manual Test Data

Sample users, products, variants, and carts for exercising the auth, catalog, and cart routes by hand.

Assumes the API is running at `http://127.0.0.1:8000` and the database is migrated:

```bash
docker compose up -d
uv run alembic upgrade head
uv run fastapi dev app/main.py
```

Set a base URL for the commands below:

```bash
BASE=http://127.0.0.1:8000
```

`jq` is used to pull IDs out of responses. If you do not have it, copy the `id` values manually.

---

## 1. User profiles

| Alias | Username | Email | Password | Role |
| --- | --- | --- | --- | --- |
| admin | `admin` | `admin@example.com` | `AdminPass123!` | `admin` |
| alice | `alice` | `alice@example.com` | `CustomerPass123!` | `customer` |
| bob | `bob` | `bob@example.com` | `CustomerPass123!` | `customer` |

Public registration always creates a `customer`. Promote the admin afterwards.

### Register

```bash
curl -sS -X POST "$BASE/api/v1/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","email":"admin@example.com","password":"AdminPass123!"}'

curl -sS -X POST "$BASE/api/v1/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"CustomerPass123!"}'

curl -sS -X POST "$BASE/api/v1/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"username":"bob","email":"bob@example.com","password":"CustomerPass123!"}'
```

### Promote the admin

```bash
uv run python -c "
from app.configs.db_connection import get_session_factory
from app.models.user_model import User, UserRole

session = get_session_factory()()
user = session.query(User).filter_by(email='admin@example.com').one()
user.role = UserRole.ADMIN
session.commit()
print(user.email, user.role)
"
```

SQL alternative (inside the Postgres container):

```bash
set -a && . ./.env && set +a

docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "update users set role = 'admin' where email = 'admin@example.com';"
```

The role is read from the database on each request, so the existing token still works after promotion.

### Get tokens

Login uses form data, with the email in the `username` field:

```bash
ADMIN_TOKEN=$(curl -sS -X POST "$BASE/api/v1/auth/login" \
  -d 'username=admin@example.com' -d 'password=AdminPass123!' | jq -r .access_token)

ALICE_TOKEN=$(curl -sS -X POST "$BASE/api/v1/auth/login" \
  -d 'username=alice@example.com' -d 'password=CustomerPass123!' | jq -r .access_token)
```

Check both profiles:

```bash
curl -sS "$BASE/api/v1/auth/me" -H "Authorization: Bearer $ADMIN_TOKEN"
curl -sS "$BASE/api/v1/auth/me" -H "Authorization: Bearer $ALICE_TOKEN"
```

---

## 2. Dataset

Every product is created as `draft`; variants are added afterwards, then published or archived.
`POST /products` does not accept nested variants — each one is added through its own route.

### Products

| Slug | Name | Description | Final status |
| --- | --- | --- | --- |
| `classic-tee` | Classic Tee | Soft cotton crew neck | `active` |
| `everyday-hoodie` | Everyday Hoodie | Fleece pullover hoodie | `draft` |
| `vintage-cap` | Vintage Cap | Washed cotton cap | `active` |
| `winter-scarf` | Winter Scarf | Wool blend scarf | `archived` |
| `sample-mug` | Sample Mug | 350 ml ceramic mug | `active` |
| `trail-sneaker` | Trail Sneaker | Lightweight trail sneaker | `active` |

`sample-mug` intentionally starts with no variants, so publishing it first returns `409`, then a variant is added and it is published.

### Variants

| SKU | Product | Name | Price | Currency | Attributes |
| --- | --- | --- | --- | --- | --- |
| `TEE-BLK-S` | classic-tee | Black / Small | 19.99 | USD | `{"color":"black","size":"S"}` |
| `TEE-BLK-M` | classic-tee | Black / Medium | 19.99 | USD | `{"color":"black","size":"M"}` |
| `TEE-WHT-M` | classic-tee | White / Medium | 21.50 | USD | `{"color":"white","size":"M"}` |
| `HOODIE-GRY-M` | everyday-hoodie | Grey / Medium | 49.00 | USD | `{"color":"grey","size":"M"}` |
| `HOODIE-NVY-L` | everyday-hoodie | Navy / Large | 52.00 | USD | `{"color":"navy","size":"L"}` |
| `CAP-NVY-OS` | vintage-cap | Navy / One Size | 15.75 | USD | `{"color":"navy","size":"OS"}` |
| `SCARF-CML-OS` | winter-scarf | Camel / One Size | 24.00 | EUR | `{"color":"camel","size":"OS"}` |
| `MUG-CREAM-350` | sample-mug | Cream / 350 ml | 12.50 | USD | `{"color":"cream","capacity":"350ml"}` |
| `SNKR-WHT-42` | trail-sneaker | White / 42 | 89.00 | EUR | `{"color":"white","size":"42"}` |
| `SNKR-BLK-42` | trail-sneaker | Black / 42 | 95.00 | EUR | `{"color":"black","size":"42"}` |

---

## 3. Seed via the API

Run the whole block in one shell session so the ID variables survive.

```bash
BASE=http://127.0.0.1:8000
ADMIN_TOKEN="${ADMIN_TOKEN:?run the login step in section 1 first}"

product() {
  curl -sS -X POST "$BASE/api/v1/admin/catalog/products" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$1" | jq -r .id
}

variant() {
  curl -sS -X POST "$BASE/api/v1/admin/catalog/products/$1/variants" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$2" | jq -r .id
}
```

### Create products

```bash
TEE=$(product '{"slug":"classic-tee","name":"Classic Tee","description":"Soft cotton crew neck"}')
HOODIE=$(product '{"slug":"everyday-hoodie","name":"Everyday Hoodie","description":"Fleece pullover hoodie"}')
CAP=$(product '{"slug":"vintage-cap","name":"Vintage Cap","description":"Washed cotton cap"}')
SCARF=$(product '{"slug":"winter-scarf","name":"Winter Scarf","description":"Wool blend scarf"}')
MUG=$(product '{"slug":"sample-mug","name":"Sample Mug","description":"350 ml ceramic mug"}')
SNEAKER=$(product '{"slug":"trail-sneaker","name":"Trail Sneaker","description":"Lightweight trail sneaker"}')
```

### Add variants

```bash
variant "$TEE" '{"sku":"TEE-BLK-S","name":"Black / Small","price":"19.99","currency":"USD","attributes":{"color":"black","size":"S"}}'
variant "$TEE" '{"sku":"TEE-BLK-M","name":"Black / Medium","price":"19.99","currency":"USD","attributes":{"color":"black","size":"M"}}'
variant "$TEE" '{"sku":"TEE-WHT-M","name":"White / Medium","price":"21.50","currency":"USD","attributes":{"color":"white","size":"M"}}'

variant "$HOODIE" '{"sku":"HOODIE-GRY-M","name":"Grey / Medium","price":"49.00","currency":"USD","attributes":{"color":"grey","size":"M"}}'
variant "$HOODIE" '{"sku":"HOODIE-NVY-L","name":"Navy / Large","price":"52.00","currency":"USD","attributes":{"color":"navy","size":"L"}}'

variant "$CAP" '{"sku":"CAP-NVY-OS","name":"Navy / One Size","price":"15.75","currency":"USD","attributes":{"color":"navy","size":"OS"}}'

variant "$SCARF" '{"sku":"SCARF-CML-OS","name":"Camel / One Size","price":"24.00","currency":"EUR","attributes":{"color":"camel","size":"OS"}}'

variant "$SNEAKER" '{"sku":"SNKR-WHT-42","name":"White / 42","price":"89.00","currency":"EUR","attributes":{"color":"white","size":"42"}}'
variant "$SNEAKER" '{"sku":"SNKR-BLK-42","name":"Black / 42","price":"95.00","currency":"EUR","attributes":{"color":"black","size":"42"}}'
```

### Publish and archive

```bash
# Expected: 409, because sample-mug has no variants yet.
curl -sS -X PATCH "$BASE/api/v1/admin/catalog/products/$MUG/publish" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Add its variant, then publish.
variant "$MUG" '{"sku":"MUG-CREAM-350","name":"Cream / 350 ml","price":"12.50","currency":"USD","attributes":{"color":"cream","capacity":"350ml"}}'

for id in "$TEE" "$MUG" "$CAP" "$SNEAKER"; do
  curl -sS -X PATCH "$BASE/api/v1/admin/catalog/products/$id/publish" \
    -H "Authorization: Bearer $ADMIN_TOKEN" | jq '{slug, status}'
done

# Exercise both transitions, then leave it archived.
curl -sS -X PATCH "$BASE/api/v1/admin/catalog/products/$SCARF/publish" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '{slug, status}'

curl -sS -X PATCH "$BASE/api/v1/admin/catalog/products/$SCARF/archive" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '{slug, status}'
```

`everyday-hoodie` stays a draft.

---

## 4. Verification

### Public catalog

| Request | Expected |
| --- | --- |
| `GET /api/v1/catalog/products` | `200`, `total: 4` |
| `GET /api/v1/catalog/products?limit=2&offset=1` | `200`, 2 items |
| `GET /api/v1/catalog/product/classic-tee` | `200`, 3 variants |
| `GET /api/v1/catalog/product/everyday-hoodie` | `404` (draft) |
| `GET /api/v1/catalog/product/winter-scarf` | `404` (archived) |
| `GET /api/v1/catalog/variant/TEE-BLK-S` | `200` |
| `GET /api/v1/catalog/variant/SCARF-CML-OS` | `404` (archived product) |

```bash
curl -sS "$BASE/api/v1/catalog/products" | jq '{total, slugs: [.items[].slug]}'
curl -sS "$BASE/api/v1/catalog/product/classic-tee" | jq '{slug, status, variants: [.variants[].sku]}'
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/api/v1/catalog/product/winter-scarf"
```

### Admin catalog

| Request | Expected |
| --- | --- |
| `GET /admin/catalog/products` | all 6, any status |
| `GET /admin/catalog/products?status=draft` | only `everyday-hoodie` |
| `GET /admin/catalog/products?status=active` | 4 products |
| `GET /admin/catalog/products?status=archived` | only `winter-scarf` |
| `GET /admin/catalog/products?status=draft&status=active` | 5 products |
| `GET /admin/catalog/products/{id}` | any status, including variants |
| `GET /admin/catalog/products?status=foo` | `422` |

```bash
curl -sS "$BASE/api/v1/admin/catalog/products" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '{total, items: [.items[] | {slug, status}]}'

curl -sS --get "$BASE/api/v1/admin/catalog/products" \
  --data-urlencode "status=draft" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '{total, slugs: [.items[].slug]}'
```

### Auth guards

| Request | Expected |
| --- | --- |
| admin route without a token | `401` |
| admin route with Alice's customer token | `403` |

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/api/v1/admin/catalog/products"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/api/v1/admin/catalog/products" \
  -H "Authorization: Bearer $ALICE_TOKEN"
```

### Cart

The cart is per customer and is created on the first cart request. Pick `ALICE_TOKEN` and US-dollar variants for the walkthrough; the dataset also contains EUR variants, and phase one assumes one currency per cart.

```bash
TEE_VARIANT=$(curl -sS "$BASE/api/v1/catalog/variant/TEE-BLK-S" | jq -r .id)
CAP_VARIANT=$(curl -sS "$BASE/api/v1/catalog/variant/CAP-NVY-OS" | jq -r .id)

# First GET creates an empty cart.
curl -sS "$BASE/api/v1/cart" -H "Authorization: Bearer $ALICE_TOKEN" \
  | jq '{id, total_quantity, subtotal, currency, items}'

# Add two tees; POST is a delta.
curl -sS -X POST "$BASE/api/v1/cart/items" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"variant_id\":\"$TEE_VARIANT\",\"quantity\":2}" \
  | jq '{total_quantity, subtotal, currency, items: [.items[] | {sku: .variant.sku, quantity, line_total}]}'

# Add one cap; a second line appears.
CART=$(curl -sS -X POST "$BASE/api/v1/cart/items" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"variant_id\":\"$CAP_VARIANT\",\"quantity\":1}")
echo "$CART" | jq '{total_quantity, subtotal, currency, items: [.items[] | {sku: .variant.sku, quantity, line_total}]}'

# PATCH sets an absolute quantity and is idempotent.
TEE_ITEM=$(echo "$CART" | jq -r '.items[] | select(.variant.sku=="TEE-BLK-S") | .id')
curl -sS -X PATCH "$BASE/api/v1/cart/items/$TEE_ITEM" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"quantity":5}' \
  | jq '{total_quantity, subtotal, items: [.items[] | {sku: .variant.sku, quantity, line_total}]}'

# DELETE removes the line; a repeat delete returns 404.
curl -sS -o /dev/null -w '%{http_code}\n' \
  -X DELETE "$BASE/api/v1/cart/items/$TEE_ITEM" \
  -H "Authorization: Bearer $ALICE_TOKEN"
# 204
```

Expected checks:

| Request | Expected |
| --- | --- |
| First `GET /cart` | `200`, `items: []`, `total_quantity: 0`, `subtotal: "0.00"`, `currency: null` |
| Add `TEE-BLK-S` x2 | one line, `total_quantity: 2`, `subtotal: "39.98"`, `currency: "USD"` |
| Add `CAP-NVY-OS` x1 | two lines, `total_quantity: 3`, `subtotal: "55.73"` |
| `PATCH` tee to `5` | `total_quantity: 6`, `subtotal: "115.70"` |
| `DELETE` tee line | `204`; fetching returns only the cap |
| Add `quantity: 100` | `422` |
| `GET /api/v1/catalog/variant/HOODIE-GRY-M` | `404` (draft product, so not addable to a cart) |
| `GET /cart` with Bob's token | separate, empty cart |

---

## 5. Handy mutations

### Update a product

`PATCH` accepts only the fields you send:

```bash
curl -sS -X PATCH "$BASE/api/v1/admin/catalog/products/$TEE" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Classic Tee (Updated)","description":"Heavier cotton"}' | jq '{slug, name, description}'
```

### Update a variant

```bash
VARIANT_ID=$(curl -sS "$BASE/api/v1/admin/catalog/products/$TEE" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.variants[] | select(.sku=="TEE-BLK-S") | .id')

curl -sS -X PATCH "$BASE/api/v1/admin/catalog/products/$TEE/variants/$VARIANT_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"price":"17.99","attributes":{"color":"black","size":"S","material":"cotton"}}' \
  | jq '{sku, price, attributes}'
```

### Add and delete a throwaway variant

```bash
EXTRA=$(variant "$TEE" '{"sku":"TEE-BLK-XL","name":"Black / XL","price":"19.99","currency":"USD","attributes":{"color":"black","size":"XL"}}')

curl -sS -o /dev/null -w '%{http_code}\n' \
  -X DELETE "$BASE/api/v1/admin/catalog/products/$TEE/variants/$EXTRA" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
# 204
```

---

## 6. Edge cases to try

| Case | Command | Expected |
| --- | --- | --- |
| Duplicate product slug | create `classic-tee` again | `409` |
| Duplicate SKU | add `TEE-BLK-S` to `vintage-cap` | `409` |
| Publish with no variants | create a product, publish immediately | `409` |
| Invalid status filter | `?status=foo` | `422` |
| Invalid slug | create with `"My Product"` | `422` |
| Lowercase currency | variant with `"usd"` | `422` |

```bash
curl -sS -X POST "$BASE/api/v1/admin/catalog/products" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"slug":"classic-tee","name":"Duplicate"}'

curl -sS -X POST "$BASE/api/v1/admin/catalog/products/$CAP/variants" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"sku":"TEE-BLK-S","name":"Duplicate","price":"1.00","currency":"USD"}'
```

Only send fields you intend to change in `PATCH` bodies; do not send `null` for `slug`, `name`, `sku`, `price`, or `currency`.

---

## 7. Cleanup

Remove the seed data:

```bash
set -a && . ./.env && set +a

docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
delete from products
where slug in ('classic-tee','everyday-hoodie','vintage-cap',
               'winter-scarf','sample-mug','trail-sneaker');

delete from users
where email in ('admin@example.com','alice@example.com','bob@example.com');
"
```

Product variants are removed by the `ondelete="CASCADE"` foreign key.

Full dev reset (destroys every row in these tables):

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "truncate table cart_items, carts, product_variants, products, users restart identity cascade;"
```
