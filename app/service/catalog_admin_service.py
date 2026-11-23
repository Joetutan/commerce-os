from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.models.catalog_model import ProductStatus
from app.repository.catalog_admin_repository import CatalogAdminRepository
from app.schemas.catalog_schema import (
    PaginatedProducts,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    VariantCreate,
    VariantResponse,
    VariantUpdate,
)


class CatalogAdminService:
    def __init__(self, repository: CatalogAdminRepository) -> None:
        self.repository = repository

    def create_product(self, data: ProductCreate) -> ProductResponse:
        if self.repository.get_product_by_slug(data.slug) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product slug already exists",
            )
        try:
            product = self.repository.create_product(
                slug=data.slug, name=data.name, description=data.description
            )
            self.repository.commit()
        except IntegrityError as exc:
            self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Catalog conflict"
            ) from exc
        return ProductResponse.model_validate(product)

    def add_variant(self, product_id: UUID, data: VariantCreate) -> VariantResponse:
        product = self.get_product(product_id=product_id)
        if self.repository.get_variant_by_sku(data.sku) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Variant sku already exists",
            )
        try:
            variant = self.repository.add_variant(product, data)
            self.repository.commit()
        except IntegrityError as exc:
            self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Variant sku already exists",
            ) from exc
        return VariantResponse.model_validate(variant)

    def list_products(
        self,
        limit: int,
        offset: int,
        status: list[ProductStatus] | None,
    ) -> PaginatedProducts:
        items, total = self.repository.get_all_products(
            limit=limit, offset=offset, status=status
        )
        products = [ProductResponse.model_validate(item) for item in items]
        return PaginatedProducts(
            items=products,
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_product(self, product_id: UUID) -> ProductResponse:
        product = self.repository.get_product_by_id(product_id=product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
            )
        return product

    def update_status_active(self, product_id: UUID) -> ProductResponse:
        product = self.get_product(product_id=product_id)
        if not product.variants:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot publish a product without variants",
            )
        product.status = ProductStatus.ACTIVE
        self.repository.update_product(product)
        self.repository.commit()
        return ProductResponse.model_validate(product)

    def update_status_archive(self, product_id: UUID) -> ProductResponse:
        product = self.get_product(product_id=product_id)
        product.status = ProductStatus.ARCHIVED
        self.repository.update_product(product)
        self.repository.commit()
        return ProductResponse.model_validate(product)

    def update_variant(
        self, product_id: UUID, variant_id: UUID, data: VariantUpdate
    ) -> VariantResponse:
        variant = self.repository.get_product_variant(
            product_id=product_id, variant_id=variant_id
        )

        if variant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found"
            )

        updates = data.model_dump(exclude_unset=True)

        if "sku" in updates:
            existing = self.repository.get_variant_by_sku(updates["sku"])
            if existing is not None and existing.id != variant.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Variant sku already exists",
                )
        for field, value in updates.items():
            setattr(variant, field, value)

        try:
            self.repository.update_variant(variant)
            self.repository.commit()
        except IntegrityError as exc:
            self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Variant sku already exists",
            ) from exc

        return VariantResponse.model_validate(variant)

    def update_product(self, product_id: UUID, data: ProductUpdate) -> ProductResponse:
        product = self.get_product(product_id=product_id)
        updates = data.model_dump(exclude_unset=True)

        if "slug" in updates:
            existing = self.repository.get_product_by_slug(updates["slug"])
            if existing is not None and existing.id != product.id:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "Product slug already exists"
                )

        for field, value in updates.items():
            setattr(product, field, value)
        try:
            updated_product = self.repository.update_product(product)
            self.repository.commit()
        except IntegrityError as exc:
            self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Catalog conflict"
            ) from exc
        return ProductResponse.model_validate(updated_product)

    def delete_product(self, product_id: UUID) -> ProductResponse:
        product = self.get_product(product_id=product_id)
        try:
            deleted_product = self.repository.delete_product(product)
            self.repository.commit()
        except IntegrityError as exc:
            self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Catalog conflict"
            ) from exc
        return ProductResponse.model_validate(deleted_product)

    def delete_variant(self, product_id: UUID, variant_id: UUID) -> VariantResponse:
        variant = self.repository.get_product_variant(
            product_id=product_id, variant_id=variant_id
        )
        if variant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found"
            )
        try:
            deleted_variant = self.repository.delete_variant(variant)
            self.repository.commit()
        except IntegrityError as exc:
            self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Catalog conflict"
            ) from exc
        return VariantResponse.model_validate(deleted_variant)
