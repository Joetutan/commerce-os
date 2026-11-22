from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog_model import Product, ProductStatus, ProductVariant


class CatalogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_active_products(self, limit: int, offset: int) -> tuple[list[Product], int]:
        active_filter = Product.status == ProductStatus.ACTIVE
        statement = (
            select(Product)
            .where(active_filter)
            .order_by(Product.name, Product.id)
            .limit(limit)
            .offset(offset)
        )
        items = list(self.db.scalars(statement).all())
        total = (
            self.db.scalar(
                select(func.count()).select_from(Product).where(active_filter)
            )
            or 0
        )
        return items, total

    def get_product(self, slug: str) -> Product | None:
        statement = select(Product).where(
            Product.slug == slug, Product.status == ProductStatus.ACTIVE
        )
        return self.db.scalar(statement)

    def get_variant(self, sku: str) -> ProductVariant | None:
        statement = (
            select(ProductVariant)
            .join(ProductVariant.product)
            .where(ProductVariant.sku == sku, Product.status == ProductStatus.ACTIVE)
        )
        return self.db.scalar(statement)
