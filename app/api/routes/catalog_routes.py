from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.configs.db_connection import get_db
from app.repository.catalog_repository import CatalogRepository
from app.schemas.catalog_schema import (
    PaginatedProducts,
    ProductResponse,
    VariantResponse,
)
from app.service.catalog_service import CatalogService

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


def get_catalog_service(db: Annotated[Session, Depends(get_db)]) -> CatalogService:
    return CatalogService(CatalogRepository(db))


@router.get("/products", response_model=PaginatedProducts)
def list_products(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: Annotated[CatalogService, Depends(get_catalog_service)] = ...,
) -> PaginatedProducts:
    return service.list_products(limit=limit, offset=offset)


@router.get("/product/{slug}", response_model=ProductResponse)
def get_product(
    slug: str, service: Annotated[CatalogService, Depends(get_catalog_service)]
) -> ProductResponse:
    return service.get_product(slug=slug)


@router.get("/variant/{sku}", response_model=VariantResponse)
def get_variant(
    sku: str, service: Annotated[CatalogService, Depends(get_catalog_service)]
) -> VariantResponse:
    return service.get_variant(sku=sku)
