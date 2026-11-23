from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog_model import Product, ProductStatus, ProductVariant
from app.schemas.catalog_schema import VariantCreate


class CatalogAdminRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_product(
        self,
        *,
        slug: str,
        name: str,
        description: str,
    ) -> Product:
        product = Product(
            slug=slug,
            name=name,
            description=description,
            status=ProductStatus.DRAFT,
        )
        self.db.add(product)
        self.db.flush()
        return product

    def add_variant(self, product: Product, data: VariantCreate) -> ProductVariant:
        variant = ProductVariant(
            sku=data.sku,
            name=data.name,
            price=data.price,
            currency=data.currency,
            attributes=data.attributes,
        )
        product.variants.append(variant)
        self.db.add(variant)
        self.db.flush()
        return variant

    def update_product(self, product: Product) -> Product:
        self.db.flush()
        return product

    def update_variant(self, variant: ProductVariant) -> ProductVariant:
        self.db.flush()
        return variant

    def get_product_by_slug(self, slug: str) -> Product | None:
        statement = select(Product).where(Product.slug == slug)
        return self.db.scalar(statement)

    def get_variant_by_sku(self, sku: str) -> ProductVariant | None:
        statement = select(ProductVariant).where(ProductVariant.sku == sku)
        return self.db.scalar(statement)

    def get_product_variant(self, product_id: UUID, variant_id: UUID) -> ProductVariant:
        statement = select(ProductVariant).where(
            ProductVariant.product_id == product_id,
            ProductVariant.id == variant_id,
        )
        return self.db.scalar(statement)

    def get_all_products(
        self,
        limit: int,
        offset: int,
        status: list[ProductStatus] | None,
    ) -> tuple[list[Product], int]:
        criteria = []
        if status:
            criteria.append(Product.status.in_(status))

        statement = (
            select(Product)
            .where(*criteria)
            .order_by(Product.name, Product.id)
            .limit(limit)
            .offset(offset)
        )

        items = list(self.db.scalars(statement).all())
        total = (
            self.db.scalar(select(func.count()).select_from(Product).where(*criteria))
            or 0
        )
        return items, total

    def get_product_by_id(self, product_id: UUID) -> Product | None:
        statement = select(Product).where(Product.id == product_id)
        return self.db.scalar(statement)

    def delete_product(self, product: Product) -> Product:
        self.db.delete(product)
        return product

    def delete_variant(self, variant: ProductVariant) -> ProductVariant:
        self.db.delete(variant)
        return variant

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
