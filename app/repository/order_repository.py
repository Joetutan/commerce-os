from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.order_model import Order, OrderStatus


class OrderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_orders(
        self, user_id: UUID, status: OrderStatus | None, limit: int, offset: int
    ) -> tuple[list[Order], int]:
        criteria = [Order.user_id == user_id]
        if status:
            criteria.append(Order.status == status)
        statement = (
            select(Order)
            .where(*criteria)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self.db.scalars(statement).all())
        total = (
            self.db.scalar(select(func.count()).select_from(Order).where(*criteria))
            or 0
        )
        return items, total

    def get_order_by_id(self, user_id: UUID, order_id: UUID) -> Order | None:
        statement = select(Order).where(Order.user_id == user_id, Order.id == order_id)
        return self.db.scalar(statement)

    def cancel_order(
        self, order_id: UUID, user_id: UUID, expected: OrderStatus
    ) -> bool:
        statement = (
            update(Order)
            .where(
                Order.user_id == user_id, Order.id == order_id, Order.status == expected
            )
            .values(status=OrderStatus.CANCELLED, cancelled_at=datetime.now(UTC))
        )
        return self.db.execute(statement).rowcount > 0

    def create_order(self, order: Order) -> Order:
        self.db.add(order)
        self.db.flush()
        return order

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
