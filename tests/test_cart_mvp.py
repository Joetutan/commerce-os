"""Cart tests covering the HTTP flow from auth to database and totals."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.configs.auth_security import security
from app.models.cart_model import Cart
from app.models.catalog_model import Product, ProductStatus, ProductVariant
from app.models.user_model import User

CART_URL = "/api/v1/cart"
ITEMS_URL = f"{CART_URL}/items"


def _make_user(db_session: Session, *, email: str) -> User:
    """Create a customer account and return it."""
    user = User(
        username=email.split("@")[0],
        email=email,
        password_hash="unused",
    )
    db_session.add(user)
    db_session.commit()
    return user


def _headers(user: User) -> dict[str, str]:
    """Return a bearer header for `user`."""
    token = security().create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def _make_product(
    db_session: Session,
    *,
    slug: str,
    status: ProductStatus,
    variants: list[ProductVariant],
) -> Product:
    """Create a product with variants and return it."""
    product = Product(slug=slug, name="Classic Tee", status=status)
    product.variants.extend(variants)
    db_session.add(product)
    db_session.commit()
    return product


def _variant(sku: str, name: str, price: str, **attributes: str) -> ProductVariant:
    """Build a `ProductVariant` with fixed USD currency."""
    return ProductVariant(
        sku=sku,
        name=name,
        price=Decimal(price),
        currency="USD",
        attributes=attributes,
    )


def _add(client, headers, variant_id: str, quantity: int = 1):
    """POST an add-item request."""
    return client.post(
        ITEMS_URL,
        json={"variant_id": variant_id, "quantity": quantity},
        headers=headers,
    )


def _cart(client, headers):
    """GET the current cart."""
    return client.get(CART_URL, headers=headers)


def _update(client, headers, item_id: str, quantity: int):
    """PATCH a cart item to an absolute quantity."""
    return client.patch(
        f"{ITEMS_URL}/{item_id}",
        json={"quantity": quantity},
        headers=headers,
    )


def _remove(client, headers, item_id: str):
    """DELETE a cart item."""
    return client.delete(f"{ITEMS_URL}/{item_id}", headers=headers)


def _money(value) -> Decimal:
    """Normalize a JSON money value, whether serialized as string or number."""
    return Decimal(str(value))


@pytest.fixture
def customer(db_session: Session) -> User:
    return _make_user(db_session, email="alice@example.com")


@pytest.fixture
def headers(customer: User) -> dict[str, str]:
    return _headers(customer)


@pytest.fixture
def other_headers(db_session: Session) -> dict[str, str]:
    return _headers(_make_user(db_session, email="bob@example.com"))


@pytest.fixture
def catalog(db_session: Session) -> dict:
    """Active product with two variants plus ids used by the requests."""
    product = _make_product(
        db_session,
        slug="classic-tee",
        status=ProductStatus.ACTIVE,
        variants=[
            _variant("TEE-BLK-S", "Black / Small", "19.99", color="black", size="S"),
            _variant("CAP-NVY-OS", "Navy / One Size", "15.75", color="navy", size="OS"),
        ],
    )
    tee, cap = product.variants
    return {
        "product_id": str(product.id),
        "tee_id": str(tee.id),
        "cap_id": str(cap.id),
    }


def test_cart_routes_require_auth(client) -> None:
    item_id = uuid4()

    assert client.get(CART_URL).status_code == 401
    assert (
        client.post(
            ITEMS_URL, json={"variant_id": str(uuid4()), "quantity": 1}
        ).status_code
        == 401
    )
    assert (
        client.patch(f"{ITEMS_URL}/{item_id}", json={"quantity": 1}).status_code == 401
    )
    assert client.delete(f"{ITEMS_URL}/{item_id}").status_code == 401


def test_get_cart_creates_one_empty_cart(
    client, headers, customer: User, db_session: Session
) -> None:
    first = _cart(client, headers)

    assert first.status_code == 200
    body = first.json()
    assert body["items"] == []
    assert body["total_quantity"] == 0
    assert _money(body["subtotal"]) == Decimal("0.00")
    assert body["currency"] is None

    second = _cart(client, headers)
    assert second.json()["id"] == body["id"]

    cart_count = db_session.scalar(
        select(func.count()).select_from(Cart).where(Cart.user_id == customer.id)
    )
    assert cart_count == 1


def test_add_item_returns_cart_with_live_totals(client, headers, catalog) -> None:
    response = _add(client, headers, catalog["tee_id"], quantity=2)

    assert response.status_code == 200
    body = response.json()
    assert body["total_quantity"] == 2
    assert _money(body["subtotal"]) == Decimal("39.98")
    assert body["currency"] == "USD"
    assert len(body["items"]) == 1

    item = body["items"][0]
    assert item["quantity"] == 2
    assert _money(item["line_total"]) == Decimal("39.98")

    variant = item["variant"]
    assert variant["sku"] == "TEE-BLK-S"
    assert variant["name"] == "Black / Small"
    assert _money(variant["price"]) == Decimal("19.99")
    assert variant["currency"] == "USD"
    assert variant["attributes"] == {"color": "black", "size": "S"}
    assert variant["product"] == {
        "id": catalog["product_id"],
        "slug": "classic-tee",
        "name": "Classic Tee",
    }


def test_adding_same_variant_increments_quantity(client, headers, catalog) -> None:
    _add(client, headers, catalog["tee_id"], quantity=1)
    body = _add(client, headers, catalog["tee_id"], quantity=1).json()

    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 2
    assert body["total_quantity"] == 2
    assert _money(body["subtotal"]) == Decimal("39.98")


def test_two_variants_are_separate_lines(client, headers, catalog) -> None:
    _add(client, headers, catalog["tee_id"], quantity=2)
    body = _add(client, headers, catalog["cap_id"], quantity=1).json()

    assert len(body["items"]) == 2
    assert {item["variant"]["sku"] for item in body["items"]} == {
        "TEE-BLK-S",
        "CAP-NVY-OS",
    }
    assert body["total_quantity"] == 3
    assert _money(body["subtotal"]) == Decimal("55.73")


def test_add_unknown_variant_returns_404(client, headers) -> None:
    response = _add(client, headers, str(uuid4()))

    assert response.status_code == 404
    assert response.json()["detail"] == "Variant not found"


def test_add_variant_from_draft_product_returns_404(
    client, headers, db_session: Session
) -> None:
    product = _make_product(
        db_session,
        slug="draft-tee",
        status=ProductStatus.DRAFT,
        variants=[_variant("DRAFT-1", "Draft", "10.00", color="black")],
    )

    response = _add(client, headers, str(product.variants[0].id))

    assert response.status_code == 404
    assert response.json()["detail"] == "Variant not found"


def test_line_quantity_is_capped(client, headers, catalog) -> None:
    assert _add(client, headers, catalog["tee_id"], quantity=99).status_code == 200

    response = _add(client, headers, catalog["tee_id"], quantity=1)

    assert response.status_code == 409
    assert response.json()["detail"] == "Quantity limit exceeded"
    assert _cart(client, headers).json()["items"][0]["quantity"] == 99


def test_add_quantity_above_schema_limit_returns_422(client, headers, catalog) -> None:
    assert _add(client, headers, catalog["tee_id"], quantity=100).status_code == 422


def test_update_item_sets_absolute_quantity(client, headers, catalog) -> None:
    item_id = _add(client, headers, catalog["tee_id"], quantity=2).json()["items"][0][
        "id"
    ]

    response = _update(client, headers, item_id, quantity=5)

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["quantity"] == 5
    assert _money(body["items"][0]["line_total"]) == Decimal("99.95")
    assert body["total_quantity"] == 5

    # Absolute set: repeating the same request does not change the quantity.
    again = _update(client, headers, item_id, quantity=5)
    assert again.json()["items"][0]["quantity"] == 5


def test_update_item_below_schema_limit_returns_422(client, headers, catalog) -> None:
    item_id = _add(client, headers, catalog["tee_id"]).json()["items"][0]["id"]

    assert _update(client, headers, item_id, quantity=0).status_code == 422


def test_update_missing_item_returns_404(client, headers, catalog) -> None:
    _add(client, headers, catalog["tee_id"])

    response = _update(client, headers, str(uuid4()), quantity=2)

    assert response.status_code == 404
    assert response.json()["detail"] == "Cart item not found"


def test_update_without_a_cart_returns_404(client, headers) -> None:
    response = _update(client, headers, str(uuid4()), quantity=2)

    assert response.status_code == 404
    assert response.json()["detail"] == "Cart not found"


def test_delete_item_removes_line_and_updates_totals(client, headers, catalog) -> None:
    tee_item_id = _add(client, headers, catalog["tee_id"], quantity=2).json()["items"][
        0
    ]["id"]
    _add(client, headers, catalog["cap_id"], quantity=1)

    response = _remove(client, headers, tee_item_id)

    assert response.status_code == 204
    body = _cart(client, headers).json()
    assert [item["variant"]["sku"] for item in body["items"]] == ["CAP-NVY-OS"]
    assert body["total_quantity"] == 1
    assert _money(body["subtotal"]) == Decimal("15.75")

    assert _remove(client, headers, tee_item_id).status_code == 404


def test_delete_without_a_cart_returns_404(client, headers) -> None:
    response = _remove(client, headers, str(uuid4()))

    assert response.status_code == 404
    assert response.json()["detail"] == "Cart not found"


def test_cart_is_scoped_to_the_authenticated_user(
    client, headers, other_headers, catalog
) -> None:
    item_id = _add(client, headers, catalog["tee_id"], quantity=2).json()["items"][0][
        "id"
    ]

    other_cart = _cart(client, other_headers)
    assert other_cart.status_code == 200
    assert other_cart.json()["items"] == []

    assert _update(client, other_headers, item_id, quantity=5).status_code == 404
    assert _remove(client, other_headers, item_id).status_code == 404

    owner_cart = _cart(client, headers).json()
    assert owner_cart["items"][0]["quantity"] == 2
