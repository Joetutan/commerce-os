from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.configs.db_connection import get_db
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
from app.service.catalog_admin_service import CatalogAdminService
from app.utils.auth_dependencies import require_admin

router = APIRouter(
    prefix="/api/v1/admin/catalog",
    tags=["catalog-admin"],
    dependencies=[Depends(require_admin)],
)


def get_catalog_admin_service(
    db: Annotated[Session, Depends(get_db)],
) -> CatalogAdminService:
    return CatalogAdminService(CatalogAdminRepository(db))


@router.post(
    "/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED
)
def create_product(
    data: ProductCreate,
    service: Annotated[CatalogAdminService, Depends(get_catalog_admin_service)],
) -> ProductResponse:
    return service.create_product(data=data)


@router.get("/products", response_model=PaginatedProducts)
def list_products(
    service: Annotated[CatalogAdminService, Depends(get_catalog_admin_service)],
    status: Annotated[list[ProductStatus] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedProducts:
    return service.list_products(limit=limit, offset=offset, status=status)


@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: UUID,
    service: Annotated[CatalogAdminService, Depends(get_catalog_admin_service)],
) -> ProductResponse:
    return ProductResponse.model_validate(service.get_product(product_id=product_id))


@router.patch("/products/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: UUID,
    data: ProductUpdate,
    service: Annotated[CatalogAdminService, Depends(get_catalog_admin_service)],
) -> ProductResponse:
    return service.update_product(product_id=product_id, data=data)


@router.patch("/products/{product_id}/publish", response_model=ProductResponse)
def publish_product(
    product_id: UUID,
    service: Annotated[CatalogAdminService, Depends(get_catalog_admin_service)],
) -> ProductResponse:
    return service.update_status_active(product_id=product_id)


@router.patch("/products/{product_id}/archive", response_model=ProductResponse)
def archive_product(
    product_id: UUID,
    service: Annotated[CatalogAdminService, Depends(get_catalog_admin_service)],
) -> ProductResponse:
    return service.update_status_archive(product_id=product_id)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: UUID,
    service: Annotated[CatalogAdminService, Depends(get_catalog_admin_service)],
) -> None:
    service.delete_product(product_id=product_id)


@router.post(
    "/products/{product_id}/variants",
    response_model=VariantResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_variant(
    product_id: UUID,
    data: VariantCreate,
    service: Annotated[CatalogAdminService, Depends(get_catalog_admin_service)],
) -> VariantResponse:
    return service.add_variant(product_id=product_id, data=data)


@router.patch("/products/{product_id}/variants/{variant_id}")
def update_variant(
    data: VariantUpdate,
    product_id: UUID,
    variant_id: UUID,
    service: Annotated[CatalogAdminService, Depends(get_catalog_admin_service)],
) -> VariantResponse:
    return service.update_variant(
        product_id=product_id, variant_id=variant_id, data=data
    )


@router.delete(
    "/products/{product_id}/variants/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_variant(
    product_id: UUID,
    variant_id: UUID,
    service: Annotated[CatalogAdminService, Depends(get_catalog_admin_service)],
) -> None:
    service.delete_variant(product_id=product_id, variant_id=variant_id)
