from decimal import Decimal
from re import fullmatch
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.catalog_model import ProductStatus


class VariantCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    attributes: dict[str, str] = Field(default_factory=dict)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        """Trim the SKU and reject characters that break lookups."""
        value = value.strip()
        if not fullmatch(r"[A-Za-z0-9._-]+", value):
            raise ValueError(
                "sku may contain letters, digits, dots, underscores, and hyphens"
            )
        return value


class ProductCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    variants: list[VariantCreate] = Field(default_factory=list, min_length=1)

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        """Normalize to lowercase kebab-case so URLs stay stable."""
        value = value.strip().lower()
        if not fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
            raise ValueError("slug must be lowercase kebab-case")
        return value


class VariantResponse(BaseModel):
    id: UUID
    sku: str
    name: str
    price: Decimal
    currency: str
    attributes: dict[str, str]
    model_config = {"from_attributes": True}


class ProductResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None
    status: ProductStatus
    variants: list[VariantResponse]
    model_config = {"from_attributes": True}


class PaginatedProducts(BaseModel):
    items: list[ProductResponse]
    total: int
    limit: int
    offset: int
