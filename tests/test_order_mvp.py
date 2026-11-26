"""Order tests covering checkout, list, detail, and cancel over HTTP."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.configs.auth_security import security
from app.models.catalog_model import Product, ProductStatus, ProductVariant
from app.models.order_model import Order, OrderStatus
from app.models.user_model import User

ORDERS_URL = "/api/v1/orders"
CHECKOUT_URL = f"{ORDERS_URL}/checkout"
CART_URL = "/api/v1/cart"
CART_ITEMS_URL = f"{CART_URL}/items"


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


def _variant(sku: str, name: str, price: str, **attributes: str) -> ProductVariant:
    """Build a USD variant."""
    return ProductVariant(
        sku=sku,
        name=name,
        price=Decimal(price),
        currency="USD",
        attributes=attributes,
    )


def _make_catalog(db_session: Session) -> dict:
    """Create an active product with two variants."""
    product = Product(
        slug="classic-tee",
        name="Classic Tee",
        status=ProductStatus.ACTIVE,
    )
    product.variants.extend(
        [
            _variant("TEE-BLK-S", "Black / Small", "19.99", color="black", size="S"),
            _variant("CAP-NVY-OS", "Navy / One Size", "15.75", color="navy", size="OS"),
        ]
    )
    db_session.add(product)
    db_session.commit()
    tee, cap = product.variants
    return {"product": product, "tee": tee, "cap": cap}


def _add_to_cart(client, headers, variant_id, quantity: int = 1):
    """Add a variant to the current cart."""
    response = client.post(
        CART_ITEMS_URL,
        json={"variant_id": str(variant_id), "quantity": quantity},
        headers=headers,
    )
    assert response.status_code == 200
    return response


def _checkout(client, headers):
    """POST a checkout request."""
    return client.post(CHECKOUT_URL, headers=headers)


def _checkout_order(client, headers, variant_id, quantity: int = 1) -> dict:
    """Add one line to the cart, check out, and return the order body."""
    _add_to_cart(client, headers, variant_id, quantity=quantity)
    response = _checkout(client, headers)
    assert response.status_code == 201
    return response.json()


def _cancel(client, headers, order_id):
    """POST a cancel request for one order."""
    return client.post(f"{ORDERS_URL}/{order_id}/cancel", headers=headers)


def _money(value) -> Decimal:
    """Normalize a JSON money value, whether serialized as string or number."""
    return Decimal(str(value))


def _set_created_at(db_session: Session, order_id: str, value: datetime) -> None:
    """Pin `created_at` so newest-first ordering is deterministic."""
    order = db_session.get(Order, UUID(order_id))
    order.created_at = value
    db_session.commit()


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
    return _make_catalog(db_session)


def test_order_routes_require_auth(client) -> None:
    order_id = uuid4()

    assert client.post(CHECKOUT_URL).status_code == 401
    assert client.get(ORDERS_URL).status_code == 401
    assert client.get(f"{ORDERS_URL}/{order_id}").status_code == 401
    assert client.post(f"{ORDERS_URL}/{order_id}/cancel").status_code == 401


def test_checkout_creates_order_from_cart(client, headers, catalog) -> None:
    _add_to_cart(client, headers, catalog["tee"].id, quantity=2)
    _add_to_cart(client, headers, catalog["cap"].id, quantity=1)

    response = _checkout(client, headers)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["currency"] == "USD"
    assert _money(body["subtotal"]) == Decimal("55.73")
    assert _money(body["total"]) == Decimal("55.73")
    assert body["total_quantity"] == 3
    assert body["cancelled_at"] is None
    assert len(body["items"]) == 2

    tee = next(item for item in body["items"] if item["variant_sku"] == "TEE-BLK-S")
    assert tee["product_slug"] == "classic-tee"
    assert tee["product_name"] == "Classic Tee"
    assert tee["attributes"] == {"color": "black", "size": "S"}
    assert _money(tee["unit_price"]) == Decimal("19.99")
    assert tee["quantity"] == 2
    assert _money(tee["line_total"]) == Decimal("39.98")

    # Checkout consumes the cart.
    assert client.get(CART_URL, headers=headers).json()["items"] == []


def test_checkout_without_a_cart_returns_409(client, headers) -> None:
    response = _checkout(client, headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Cart is empty"


def test_checkout_twice_returns_409(client, headers, catalog) -> None:
    _checkout_order(client, headers, catalog["tee"].id)

    response = _checkout(client, headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Cart is empty"


def test_checkout_rejects_archived_product(
    client, headers, catalog, db_session
) -> None:
    _add_to_cart(client, headers, catalog["tee"].id)

    product = db_session.get(Product, catalog["product"].id)
    product.status = ProductStatus.ARCHIVED
    db_session.commit()

    response = _checkout(client, headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Item TEE-BLK-S is no longer available"


def test_list_orders_returns_newest_first_and_is_scoped(
    client, headers, other_headers, catalog, db_session
) -> None:
    first = _checkout_order(client, headers, catalog["tee"].id)
    second = _checkout_order(client, headers, catalog["cap"].id)
    _set_created_at(db_session, first["id"], datetime(2026, 1, 1, tzinfo=UTC))
    _set_created_at(db_session, second["id"], datetime(2026, 1, 2, tzinfo=UTC))

    response = client.get(ORDERS_URL, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [order["id"] for order in body["items"]] == [second["id"], first["id"]]

    page = client.get(f"{ORDERS_URL}?limit=1&offset=1", headers=headers).json()
    assert page["total"] == 2
    assert [order["id"] for order in page["items"]] == [first["id"]]

    other = client.get(ORDERS_URL, headers=other_headers).json()
    assert other["total"] == 0
    assert other["items"] == []


def test_list_orders_filters_by_status(client, headers, catalog) -> None:
    cancelled = _checkout_order(client, headers, catalog["tee"].id)
    assert _cancel(client, headers, cancelled["id"]).status_code == 200
    pending = _checkout_order(client, headers, catalog["cap"].id)

    pending_page = client.get(f"{ORDERS_URL}?status=pending", headers=headers).json()
    assert pending_page["total"] == 1
    assert [order["id"] for order in pending_page["items"]] == [pending["id"]]

    cancelled_page = client.get(
        f"{ORDERS_URL}?status=cancelled", headers=headers
    ).json()
    assert cancelled_page["total"] == 1
    assert [order["id"] for order in cancelled_page["items"]] == [cancelled["id"]]

    assert (
        client.get(f"{ORDERS_URL}?status=unknown", headers=headers).status_code == 422
    )


def test_get_order_returns_the_snapshot(client, headers, catalog, db_session) -> None:
    order = _checkout_order(client, headers, catalog["tee"].id, quantity=2)

    # Change the live catalog after checkout.
    product = db_session.get(Product, catalog["product"].id)
    variant = db_session.get(ProductVariant, catalog["tee"].id)
    product.name = "Renamed Tee"
    variant.price = Decimal("99.99")
    db_session.commit()

    response = client.get(f"{ORDERS_URL}/{order['id']}", headers=headers)

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["product_name"] == "Classic Tee"
    assert _money(item["unit_price"]) == Decimal("19.99")
    assert _money(item["line_total"]) == Decimal("39.98")


def test_get_order_of_another_user_returns_404(
    client, headers, other_headers, catalog
) -> None:
    order = _checkout_order(client, headers, catalog["tee"].id)

    assert (
        client.get(f"{ORDERS_URL}/{order['id']}", headers=other_headers).status_code
        == 404
    )
    assert client.get(f"{ORDERS_URL}/{uuid4()}", headers=headers).status_code == 404


def test_cancel_pending_order_sets_status_and_timestamp(
    client, headers, catalog, db_session
) -> None:
    order = _checkout_order(client, headers, catalog["tee"].id)

    response = _cancel(client, headers, order["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["cancelled_at"] is not None

    db_session.expire_all()
    stored = db_session.get(Order, UUID(order["id"]))
    assert stored.status == OrderStatus.CANCELLED
    assert stored.cancelled_at is not None


def test_cancel_non_pending_order_returns_409(
    client, headers, catalog, db_session
) -> None:
    order = _checkout_order(client, headers, catalog["tee"].id)

    stored = db_session.get(Order, UUID(order["id"]))
    stored.status = OrderStatus.FULFILLED
    db_session.commit()

    response = _cancel(client, headers, order["id"])

    assert response.status_code == 409
    assert "cannot be cancelled" in response.json()["detail"]

    db_session.expire_all()
    assert db_session.get(Order, UUID(order["id"])).status == OrderStatus.FULFILLED


def test_cancel_twice_returns_409(client, headers, catalog) -> None:
    order = _checkout_order(client, headers, catalog["tee"].id)
    assert _cancel(client, headers, order["id"]).status_code == 200

    response = _cancel(client, headers, order["id"])

    assert response.status_code == 409
    assert response.json()["detail"] == "Order is cancelled and cannot be cancelled"


def test_cancel_another_users_order_returns_404(
    client, headers, other_headers, catalog, db_session
) -> None:
    order = _checkout_order(client, headers, catalog["tee"].id)

    response = _cancel(client, other_headers, order["id"])

    assert response.status_code == 404
    db_session.expire_all()
    assert db_session.get(Order, UUID(order["id"])).status == OrderStatus.PENDING
