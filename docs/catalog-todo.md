# Catalog Todo

Remaining work for the Catalog domain. The public read-only workflow is in place; admin writes and follow-ups are below.

Current state:

- Models: `Product`, `ProductVariant`, `ProductStatus` (draft / active / archived).
- Public routes: list products, get product by slug, get variant by SKU.
- Public routes expose only `status == active`; drafts and archived rows return `404`.
- `require_admin` exists in `app/utils/auth_dependencies.py` but no route uses it yet.

## Admin endpoints

Mount under `/api/v1/admin/catalog` with `Depends(require_admin)` on the router.

### Products

- [ ] `POST /products` - create a product with nested variants. `201`.
- [ ] `GET /products` - list products in any status with `limit`/`offset` and an optional `status` filter.
- [ ] `GET /products/{product_id}` - fetch a product by id in any status, including variants.
- [ ] `PATCH /products/{product_id}` - update `name`, `description`, and `slug`.
- [ ] `POST /products/{product_id}/publish` - transition `draft`/`archived` to `active`.
- [ ] `POST /products/{product_id}/archive` - transition `active` to `archived`.
- [ ] `DELETE /products/{product_id}` - delete a product and cascade its variants.

### Variants

- [ ] `POST /products/{product_id}/variants` - add a variant to an existing product. `201`.
- [ ] `PATCH /products/{product_id}/variants/{variant_id}` - update `name`, `price`, `currency`, and `attributes`.
- [ ] `DELETE /products/{product_id}/variants/{variant_id}` - delete a variant.
- [ ] Reject deleting the last variant if the product must keep at least one.

## Supporting work

- [ ] Admin repository lookups by id that ignore status (public lookups stay active-only).
- [ ] Conflict handling for duplicate `slug` and `sku` (`409`, not `500`).
- [ ] Reject duplicate `sku` values inside a single create request.
- [ ] Status transition rules: decide which transitions are legal and return `409` for the rest.
- [ ] Admin response schemas, or reuse the public schemas with `status` populated.
- [ ] Admin route tests: `403` for customers, `401` without a token, happy path for admins.

## Public follow-ups

- [ ] Add product context to `VariantResponse` (`product_id`, `product_name`, `product_slug`) if Cart needs it to render a line.
- [ ] Decide whether the public `ProductResponse` should keep `status`, since it is always `"active"`.
- [ ] Optional: filter public product list by variant `currency` or price range.

## Known gaps

- [ ] No admin route for creating products yet, so products are only created directly through the database.
- [ ] `ProductUpdate`/`VariantUpdate` schemas do not exist.
- [ ] No pagination on the admin product list until it is added.
- [ ] No inventory linkage; stock and reservations belong to the Inventory domain.
- [ ] No image or media fields on products.
