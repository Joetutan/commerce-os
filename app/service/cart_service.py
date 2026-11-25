from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.models.cart_model import Cart
from app.repository.cart_repository import CartRepository
from app.schemas.cart_schema import (
    CartItemCreate,
    CartItemResponse,
    CartItemUpdate,
    CartResponse,
    CartVariantResponse,
)

MAX_LINE_QUANTITY = 99


class CartService:
    def __init__(self, repository: CartRepository) -> None:
        self.repository = repository

    def get_cart(self, user_id: UUID) -> Cart:
        cart = self.repository.get_cart_by_user(user_id=user_id)
        if cart is None:
            cart = self.create_cart(user_id=user_id)
        return cart

    def create_cart(self, user_id: UUID) -> Cart:
        try:
            cart = self.repository.create_cart(user_id=user_id)
            self.repository.commit()
            return cart
        except IntegrityError:
            self.repository.rollback()
            cart = self.repository.get_cart_by_user(user_id=user_id)
            if cart is None:
                raise
            return cart

    def add_item(self, user_id: UUID, data: CartItemCreate) -> CartResponse:
        variant = self.repository.get_active_variant(variant_id=data.variant_id)
        if variant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found"
            )

        cart = self.get_cart(user_id)
        item = self.repository.get_item(cart_id=cart.id, variant_id=variant.id)

        if item is None:
            try:
                self.repository.insert_item(
                    cart_id=cart.id,
                    variant_id=variant.id,
                    quantity=data.quantity,
                )
                self.repository.commit()
            except IntegrityError:
                self.repository.rollback()
                if not self.repository.increment_item(
                    cart_id=cart.id,
                    variant_id=variant.id,
                    quantity=data.quantity,
                    max_quantity=MAX_LINE_QUANTITY,
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Quantity limit exceeded",
                    )
                self.repository.commit()
        else:
            if not self.repository.increment_item(
                cart_id=cart.id,
                variant_id=variant.id,
                quantity=data.quantity,
                max_quantity=MAX_LINE_QUANTITY,
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Quantity limit exceeded",
                )
            self.repository.commit()

        return self.cart_to_response(self.repository.get_cart_by_user(user_id=user_id))

    def update_item(
        self, user_id: UUID, item_id: UUID, data: CartItemUpdate
    ) -> CartResponse:
        cart = self.repository.get_cart_by_user(user_id=user_id)
        if cart is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Cart not found"
            )

        if not self.repository.set_item_quantity(
            cart_id=cart.id, item_id=item_id, quantity=data.quantity
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found"
            )

        self.repository.commit()
        return self.cart_to_response(self.repository.get_cart_by_user(user_id=user_id))

    def delete_item(self, user_id: UUID, item_id: UUID) -> None:
        cart = self.repository.get_cart_by_user(user_id=user_id)
        if cart is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Cart not found"
            )

        if not self.repository.delete_item(cart_id=cart.id, item_id=item_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found"
            )
        self.repository.commit()

    def cart_to_response(self, cart: Cart) -> CartResponse:
        items: list[CartItemResponse] = []
        total_quantity = 0
        subtotal = Decimal("0.00")
        currency: str | None = None

        for item in cart.items:
            variant = item.variant
            line_total = variant.price * item.quantity

            total_quantity += item.quantity
            subtotal += line_total
            currency = currency or variant.currency

            items.append(
                CartItemResponse(
                    id=item.id,
                    quantity=item.quantity,
                    line_total=line_total,
                    variant=CartVariantResponse.model_validate(variant),
                )
            )

        return CartResponse(
            id=cart.id,
            items=items,
            total_quantity=total_quantity,
            subtotal=subtotal,
            currency=currency,
        )
