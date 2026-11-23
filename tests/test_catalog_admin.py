"""Happy-path tests for the catalog admin workflow."""

import pytest
from sqlalchemy.orm import Session

from app.configs.auth_security import security
from app.models.user_model import User, UserRole

ADMIN_PRODUCTS_URL = "/api/v1/admin/catalog/products"
PUBLIC_PRODUCTS_URL = "/api/v1/catalog/products"
PUBLIC_PRODUCT_URL = "/api/v1/catalog/product"

VARIANT = {
    "sku": "TS-1",
    "name": "Default",
    "price": "21.99",
    "currency": "USD",
}


@pytest.fixture
def admin_headers(db_session: Session) -> dict[str, str]:
    """Create an admin user and return a bearer header for it."""
    admin = User(
        username="admin",
        email="admin@example.com",
        password_hash="unused",
        role=UserRole.ADMIN,
    )
    db_session.add(admin)
    db_session.commit()
    token = security().create_access_token(admin.id)
    return {"Authorization": f"Bearer {token}"}


def _create_product(client, headers, **overrides) -> dict:
    """POST a valid product and return the response body."""
    payload = {"slug": "classic-tshirt", "name": "Classic T-Shirt"}
    payload.update(overrides)
    response = client.post(ADMIN_PRODUCTS_URL, json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


def _add_variant(client, headers, product_id: str) -> dict:
    """POST a valid variant to a product and return the response body."""
    response = client.post(
        f"{ADMIN_PRODUCTS_URL}/{product_id}/variants",
        json=VARIANT,
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_create_list_and_get_product(client, admin_headers) -> None:
    product = _create_product(client, admin_headers)

    assert product["status"] == "draft"
    assert product["variants"] == []

    listed = client.get(ADMIN_PRODUCTS_URL, headers=admin_headers)
    assert listed.status_code == 200
    assert [item["slug"] for item in listed.json()["items"]] == ["classic-tshirt"]

    detail = client.get(f"{ADMIN_PRODUCTS_URL}/{product['id']}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == product["id"]

    # Drafts are not part of the public catalog.
    assert client.get(f"{PUBLIC_PRODUCT_URL}/classic-tshirt").status_code == 404
    assert client.get(PUBLIC_PRODUCTS_URL).json()["total"] == 0


def test_update_product(client, admin_headers) -> None:
    product = _create_product(client, admin_headers)

    response = client.patch(
        f"{ADMIN_PRODUCTS_URL}/{product['id']}",
        json={"name": "Renamed T-Shirt"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed T-Shirt"
    assert response.json()["slug"] == "classic-tshirt"


def test_add_variant_and_publish(client, admin_headers) -> None:
    product = _create_product(client, admin_headers)
    variant = _add_variant(client, admin_headers, product["id"])
    assert variant["sku"] == "TS-1"

    published = client.patch(
        f"{ADMIN_PRODUCTS_URL}/{product['id']}/publish", headers=admin_headers
    )

    assert published.status_code == 200
    assert published.json()["status"] == "active"

    public = client.get(f"{PUBLIC_PRODUCT_URL}/classic-tshirt")
    assert public.status_code == 200
    assert public.json()["variants"][0]["sku"] == "TS-1"


def test_update_and_delete_variant(client, admin_headers) -> None:
    product = _create_product(client, admin_headers)
    variant = _add_variant(client, admin_headers, product["id"])

    updated = client.patch(
        f"{ADMIN_PRODUCTS_URL}/{product['id']}/variants/{variant['id']}",
        json={"price": "19.99"},
        headers=admin_headers,
    )

    assert updated.status_code == 200
    assert updated.json()["price"] == "19.99"

    deleted = client.delete(
        f"{ADMIN_PRODUCTS_URL}/{product['id']}/variants/{variant['id']}",
        headers=admin_headers,
    )

    assert deleted.status_code == 204


def test_archive_and_delete_product(client, admin_headers) -> None:
    product = _create_product(client, admin_headers)

    archived = client.patch(
        f"{ADMIN_PRODUCTS_URL}/{product['id']}/archive", headers=admin_headers
    )

    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    deleted = client.delete(
        f"{ADMIN_PRODUCTS_URL}/{product['id']}", headers=admin_headers
    )

    assert deleted.status_code == 204
    assert (
        client.get(
            f"{ADMIN_PRODUCTS_URL}/{product['id']}", headers=admin_headers
        ).status_code
        == 404
    )
