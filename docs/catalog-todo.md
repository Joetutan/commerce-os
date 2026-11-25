# Catalog Todo

Status of the Catalog domain. Public reads and admin writes are in place; the remaining items are follow-ups.

## Current state

- Models: `Product`, `ProductVariant`, `ProductStatus` (draft / active / archived).
- Public routes: list active products, get an active product by slug, get a variant by SKU. Inactive rows return `404`.
- Admin routes live under `/api/v1/admin/catalog` with router-level `Depends(require_admin)`.
- Creating a product always produces a `draft`; publishing and archiving are separate `PATCH` actions.
- Admin create accepts no nested variants; each variant is added through its own route.
- Admin list supports `limit`/`offset` and repeated `status` filters.

## Admin endpoints

### Products

- [x] `POST /products` - create a draft product. `201`.
- [x] `GET /products` - list products in any status with `limit`/`offset` and optional repeated `status` filters.
- [x] `GET /products/{product_id}` - fetch a product by id in any status, including variants.
- [x] `PATCH /products/{product_id}` - partial update of `slug`, `name`, and `description`.
- [x] `PATCH /products/{product_id}/publish` - requires at least one variant; returns `409` otherwise.
- [x] `PATCH /products/{product_id}/archive` - move a product to `archived`.
- [x] `DELETE /products/{product_id}` - `204`; cascades variants.

### Variants

- [x] `POST /products/{product_id}/variants` - add a variant to an existing product. `201`.
- [x] `PATCH /products/{product_id}/variants/{variant_id}` - partial update of `sku`, `name`, `price`, `currency`, and `attributes`.
- [x] `DELETE /products/{product_id}/variants/{variant_id}` - `204`.
- [ ] Reject deleting the last variant of an active product.

## Supporting work

- [x] Admin repository lookups by id that ignore status; public lookups stay active-only.
- [x] Duplicate `slug` and `sku` return `409`.
- [x] Reuse the public response schemas with `status` populated.
- [x] Router-level `require_admin` (`401` without a token, `403` for customers).
- [x] Admin happy-path suite in `tests/test_catalog_admin.py`.
- [ ] Negative admin tests: `401`, `403`, `404`, `409`, `422`.
- [ ] Status transition matrix; publish and archive currently accept most transitions.
- [ ] Reject explicit `null` for non-nullable update fields; it currently reaches the validators or database and returns `500`.
- [ ] Admin variant listing route if a future UI needs to fetch variants without the product.

## Public follow-ups

- [ ] Add product context to `VariantResponse` (`product_id`, `product_name`, `product_slug`) if Cart needs it to render a line.
- [ ] Decide whether the public `ProductResponse` should keep `status`, since it is always `"active"`.
- [ ] Optional: filter the public product list by variant `currency` or price range.

## Known gaps

- [ ] No inventory linkage; stock and reservations belong to the Inventory domain.
- [ ] No image or media fields on products.
- [ ] No cart integration yet; Cart will reference variants and read live pricing.
