from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class CartItemCreate(BaseModel):
    variant_id: UUID
    quantity: int = Field(default=1, ge=1, le=99)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=99)


class CartProductResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    model_config = {"from_attributes": True}


class CartVariantResponse(BaseModel):
    id: UUID
    sku: str
    name: str
    price: Decimal
    currency: str
    attributes: dict[str, str]
    product: CartProductResponse
    model_config = {"from_attributes": True}


class CartItemResponse(BaseModel):
    id: UUID
    quantity: int
    variant: CartVariantResponse
    line_total: Decimal
    model_config = {"from_attributes": True}


class CartResponse(BaseModel):
    id: UUID
    items: list[CartItemResponse]
    total_quantity: int
    subtotal: Decimal
    currency: str | None
