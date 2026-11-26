from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.configs.db_connection import Base


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    # Table-level schema: named constraints and composite indexes. Column
    # arguments (nullable, default, index=True) cannot express these.
    __table_args__ = (
        # Money guards: the service validates too, but the database is the
        # last line of defence for scripts, races, and future callers.
        CheckConstraint("subtotal >= 0", name="ck_orders_subtotal_non_negative"),
        CheckConstraint("total >= 0", name="ck_orders_total_non_negative"),
        # Serves the "my orders, newest first" query:
        # WHERE user_id = ... ORDER BY created_at DESC.
        Index("ix_orders_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(
            OrderStatus,
            name="ck_orders_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            length=20,
        ),
        nullable=False,
        default=OrderStatus.PENDING,
        server_default=OrderStatus.PENDING.value,
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        order_by="OrderItem.created_at",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint(
            "unit_price >= 0", name="ck_order_items_unit_price_non_negative"
        ),
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    product_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    variant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True
    )
    product_slug: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_sku: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    variant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    attributes: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    order: Mapped[Order] = relationship(back_populates="items")
