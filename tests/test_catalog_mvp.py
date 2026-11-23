"""Catalog tests covering the public product and variant workflow."""

from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.catalog_model import Product, ProductStatus, ProductVariant
from app.schemas.catalog_schema import ProductCreate, VariantCreate

PRODUCTS_URL = "/api/v1/catalog/products"
PRODUCT_URL = "/api/v1/catalog/product"
VARIANT_URL = "/api/v1/catalog/variant"


def _create_product(
    db_session: Session,
    *,
    slug: str,
    name: str | None = None,
    status: ProductStatus = ProductStatus.ACTIVE,
    sku: str | None = None,
    price: Decimal = Decimal("9.99"),
) -> Product:
    """Insert a product with one variant and return it."""
    product = Product(
        slug=slug,
        name=name or slug.replace("-", " ").title(),
        status=status,
    )
    product.variants.append(
        ProductVariant(
            sku=sku or f"{slug.upper()}-1",
            name="Default",
            price=price,
            currency="USD",
        )
    )
    db_session.add(product)
    db_session.commit()
    return product


def test_list_products_returns_only_active(client, db_session) -> None:
    _create_product(db_session, slug="active-product")
    _create_product(db_session, slug="draft-product", status=ProductStatus.DRAFT)
    _create_product(db_session, slug="archived-product", status=ProductStatus.ARCHIVED)

    response = client.get(PRODUCTS_URL)

    assert response.status_code == 200
    body = response.json()
    assert [item["slug"] for item in body["items"]] == ["active-product"]
    assert body["total"] == 1
    assert body["limit"] == 20
    assert body["offset"] == 0


def test_list_products_paginates(client, db_session) -> None:
    for slug in ["alpha", "bravo", "charlie"]:
        _create_product(db_session, slug=slug)

    response = client.get(PRODUCTS_URL, params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert [item["slug"] for item in body["items"]] == ["bravo"]
    assert body["total"] == 3
    assert body["limit"] == 1
    assert body["offset"] == 1


def test_list_products_returns_empty_page(client) -> None:
    response = client.get(PRODUCTS_URL)

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
    }


def test_get_product_returns_active_product(client, db_session) -> None:
    product = _create_product(
        db_session,
        slug="classic-tshirt",
        name="Classic T-Shirt",
        sku="TS-1",
        price=Decimal("21.99"),
    )

    response = client.get(f"{PRODUCT_URL}/classic-tshirt")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(product.id),
        "slug": "classic-tshirt",
        "name": "Classic T-Shirt",
        "description": None,
        "status": "active",
        "variants": [
            {
                "id": str(product.variants[0].id),
                "sku": "TS-1",
                "name": "Default",
                "price": "21.99",
                "currency": "USD",
                "attributes": {},
            }
        ],
    }


@pytest.mark.parametrize(
    "product_status", [ProductStatus.DRAFT, ProductStatus.ARCHIVED]
)
def test_get_product_hides_inactive_products(
    client, db_session, product_status: ProductStatus
) -> None:
    _create_product(db_session, slug="hidden-product", status=product_status)

    response = client.get(f"{PRODUCT_URL}/hidden-product")

    assert response.status_code == 404
    assert response.json() == {"detail": "Product not found"}


def test_get_product_unknown_slug_returns_404(client) -> None:
    response = client.get(f"{PRODUCT_URL}/unknown")

    assert response.status_code == 404
    assert response.json() == {"detail": "Product not found"}


def test_get_variant_returns_active_variant(client, db_session) -> None:
    product = _create_product(
        db_session,
        slug="classic-tshirt",
        sku="TS-1",
        price=Decimal("21.99"),
    )

    response = client.get(f"{VARIANT_URL}/TS-1")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(product.variants[0].id),
        "sku": "TS-1",
        "name": "Default",
        "price": "21.99",
        "currency": "USD",
        "attributes": {},
    }


@pytest.mark.parametrize(
    "product_status", [ProductStatus.DRAFT, ProductStatus.ARCHIVED]
)
def test_get_variant_hides_inactive_products(
    client, db_session, product_status: ProductStatus
) -> None:
    _create_product(
        db_session,
        slug="hidden-product",
        status=product_status,
        sku="HIDDEN-1",
    )

    response = client.get(f"{VARIANT_URL}/HIDDEN-1")

    assert response.status_code == 404
    assert response.json() == {"detail": "Variant not found"}


def test_get_variant_unknown_sku_returns_404(client) -> None:
    response = client.get(f"{VARIANT_URL}/UNKNOWN")

    assert response.status_code == 404
    assert response.json() == {"detail": "Variant not found"}


def test_product_create_normalizes_slug() -> None:
    product = ProductCreate(slug="  Classic-TShirt  ", name="Classic T-Shirt")

    assert product.slug == "classic-tshirt"


def test_product_create_allows_empty_variants() -> None:
    product = ProductCreate(slug="classic-tshirt", name="Classic T-Shirt")

    assert product.slug == "classic-tshirt"


def test_variant_create_rejects_negative_price() -> None:
    with pytest.raises(ValidationError):
        VariantCreate(
            sku="TS-1",
            name="Default",
            price=Decimal("-1.00"),
            currency="USD",
        )


def test_variant_create_rejects_lowercase_currency() -> None:
    with pytest.raises(ValidationError):
        VariantCreate(
            sku="TS-1",
            name="Default",
            price=Decimal("1.00"),
            currency="usd",
        )


def test_negative_price_violates_db_constraint(db_session) -> None:
    product = Product(slug="bad-price", name="Bad Price")
    db_session.add(product)
    db_session.flush()

    db_session.add(
        ProductVariant(
            product_id=product.id,
            sku="BAD-1",
            name="Bad",
            price=Decimal("-1.00"),
            currency="USD",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()
