from fastapi import HTTPException, status

from app.repository.catalog_repository import CatalogRepository
from app.schemas.catalog_schema import (
    PaginatedProducts,
    ProductResponse,
    VariantResponse,
)


class CatalogService:
    def __init__(self, repository: CatalogRepository) -> None:
        self.repository = repository

    def list_products(self, limit: int, offset: int) -> PaginatedProducts:
        items, total = self.repository.get_active_products(limit=limit, offset=offset)
        products = [ProductResponse.model_validate(item) for item in items]
        return PaginatedProducts(
            items=products,
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_product(self, slug: str) -> ProductResponse:
        product = self.repository.get_product(slug=slug)

        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
            )
        return ProductResponse.model_validate(product)

    def get_variant(self, sku: str) -> VariantResponse:
        variant = self.repository.get_variant(sku=sku)

        if variant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found"
            )
        return VariantResponse.model_validate(variant)
