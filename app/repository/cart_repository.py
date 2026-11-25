from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.cart_model import Cart, CartItem
from app.models.catalog_model import Product, ProductStatus, ProductVariant


class CartRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_cart_by_user(self, user_id: UUID) -> Cart | None:
        statement = (
            select(Cart)
            .where(Cart.user_id == user_id)
            .options(
                selectinload(Cart.items)
                .selectinload(CartItem.variant)
                .selectinload(ProductVariant.product)
            )
            .execution_options(populate_existing=True)
        )
        return self.db.scalar(statement)

    def create_cart(self, user_id: UUID) -> Cart:
        cart = Cart(user_id=user_id)
        self.db.add(cart)
        self.db.flush()
        return cart

    def get_active_variant(self, variant_id: UUID) -> ProductVariant | None:
        statement = (
            select(ProductVariant)
            .join(ProductVariant.product)
            .where(
                ProductVariant.id == variant_id,
                Product.status == ProductStatus.ACTIVE,
            )
            .options(selectinload(ProductVariant.product))
        )
        return self.db.scalar(statement)

    def get_item(self, cart_id: UUID, variant_id: UUID) -> CartItem | None:
        statement = select(CartItem).where(
            CartItem.cart_id == cart_id, CartItem.variant_id == variant_id
        )
        return self.db.scalar(statement)

    def increment_item(
        self, cart_id: UUID, variant_id: UUID, quantity: int, max_quantity: int
    ) -> bool:
        statement = (
            update(CartItem)
            .where(
                CartItem.cart_id == cart_id,
                CartItem.variant_id == variant_id,
                CartItem.quantity + quantity <= max_quantity,
            )
            .values(quantity=CartItem.quantity + quantity)
        )
        return self.db.execute(statement).rowcount > 0

    def set_item_quantity(self, cart_id: UUID, item_id: UUID, quantity: int) -> bool:
        statement = (
            update(CartItem)
            .where(CartItem.cart_id == cart_id, CartItem.id == item_id)
            .values(quantity=quantity)
        )
        return self.db.execute(statement).rowcount > 0

    def delete_item(self, cart_id: UUID, item_id: UUID) -> bool:
        statement = delete(CartItem).where(
            CartItem.cart_id == cart_id, CartItem.id == item_id
        )
        return self.db.execute(statement).rowcount > 0

    def insert_item(self, cart_id: UUID, variant_id: UUID, quantity: int) -> CartItem:
        item = CartItem(cart_id=cart_id, variant_id=variant_id, quantity=quantity)
        self.db.add(item)
        self.db.flush()
        return item

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
