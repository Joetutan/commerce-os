from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.models.order_model import OrderStatus


class OrderItemResponse(BaseModel):
    id: UUID
    product_slug: str
    product_name: str
    variant_sku: str
    attributes: dict[str, str]
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: UUID
    status: OrderStatus
    currency: str
    subtotal: Decimal
    total: Decimal
    total_quantity: int
    created_at: datetime
    cancelled_at: datetime | None
    items: list[OrderItemResponse]
    model_config = {"from_attributes": True}


class PaginatedOrders(BaseModel):
    items: list[OrderResponse]
    total: int
    limit: int
    offset: int
