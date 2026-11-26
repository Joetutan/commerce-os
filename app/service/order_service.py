from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status

from app.models.catalog_model import ProductStatus
from app.models.order_model import Order, OrderItem, OrderStatus
from app.models.user_model import User
from app.repository.cart_repository import CartRepository
from app.repository.order_repository import OrderRepository
from app.schemas.order_schema import OrderItemResponse, OrderResponse, PaginatedOrders


class OrderService:
    def __init__(
        self, order_repository: OrderRepository, cart_repository: CartRepository
    ) -> None:
        self.order_repository = order_repository
        self.cart_repository = cart_repository

    def list_orders(
        self, user: User, status: OrderStatus | None, limit: int, offset: int
    ) -> PaginatedOrders:
        items, total = self.order_repository.get_orders(
            user_id=user.id, status=status, limit=limit, offset=offset
        )
        orders = [self.order_to_response(item) for item in items]
        return PaginatedOrders(
            items=orders,
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_order(self, user_id: UUID, order_id: UUID) -> OrderResponse:
        order = self.order_repository.get_order_by_id(
            user_id=user_id, order_id=order_id
        )
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
            )
        return self.order_to_response(order)

    def cancel_order(self, user_id: UUID, order_id: UUID) -> OrderResponse:
        order = self.order_repository.get_order_by_id(
            user_id=user_id, order_id=order_id
        )

        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
            )

        if order.status != OrderStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Order is {order.status} and cannot be cancelled",
            )

        if not self.order_repository.cancel_order(
            order_id=order_id, user_id=user_id, expected=OrderStatus.PENDING
        ):
            self.order_repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order is no longer pending",
            )

        self.order_repository.commit()

        return self.order_to_response(
            self.order_repository.get_order_by_id(user_id=user_id, order_id=order_id)
        )

    def check_out(self, user: User) -> OrderResponse:

        cart = self.cart_repository.get_cart_for_update(user_id=user.id)
        if cart is None or not cart.items:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Cart is empty"
            )

        items: list[OrderItem] = []
        subtotal = Decimal("0.00")
        currency: str | None = None

        for item in cart.items:
            variant = item.variant
            if currency is None:
                currency = variant.currency

            if variant.product.status != ProductStatus.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Item {variant.sku} is no longer available",
                )

            subtotal += variant.price * item.quantity

            items.append(
                OrderItem(
                    product_id=variant.product_id,
                    variant_id=variant.id,
                    product_slug=variant.product.slug,
                    product_name=variant.product.name,
                    variant_sku=variant.sku,
                    variant_name=variant.name,
                    attributes=variant.attributes,
                    unit_price=variant.price,
                    quantity=item.quantity,
                )
            )

        new_order = Order(
            user_id=user.id,
            customer_email=user.email,
            status=OrderStatus.PENDING,
            subtotal=subtotal,
            total=subtotal,
            currency=currency,
            items=items,
        )

        self.order_repository.create_order(new_order)
        self.cart_repository.clear_items(cart_id=cart.id)
        self.order_repository.commit()
        return self.order_to_response(new_order)

    def order_to_response(self, order: Order) -> OrderResponse:
        items: list[OrderItemResponse] = []
        total_quantity = 0

        for item in order.items:
            line_total = item.unit_price * item.quantity
            total_quantity += item.quantity
            items.append(
                OrderItemResponse(
                    id=item.id,
                    product_slug=item.product_slug,
                    product_name=item.product_name,
                    variant_sku=item.variant_sku,
                    attributes=item.attributes,
                    unit_price=item.unit_price,
                    quantity=item.quantity,
                    line_total=line_total,
                )
            )

        return OrderResponse(
            id=order.id,
            status=order.status,
            currency=order.currency,
            subtotal=order.subtotal,
            total=order.total,
            total_quantity=total_quantity,
            created_at=order.created_at,
            cancelled_at=order.cancelled_at,
            items=items,
        )
