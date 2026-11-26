from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.configs.db_connection import get_db
from app.models.order_model import OrderStatus
from app.models.user_model import User
from app.repository.cart_repository import CartRepository
from app.repository.order_repository import OrderRepository
from app.schemas.order_schema import OrderResponse, PaginatedOrders
from app.service.order_service import OrderService
from app.utils.auth_dependencies import get_current_user


def get_order_service(db: Annotated[Session, Depends(get_db)]) -> OrderService:
    return OrderService(OrderRepository(db), CartRepository(db))


router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


# check-out, convert current user cart to order.
@router.post(
    "/checkout", response_model=OrderResponse, status_code=status.HTTP_201_CREATED
)
def check_out(
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderResponse:
    return service.check_out(user)


# List current user orders, newest first
@router.get("", response_model=PaginatedOrders)
def list_orders(
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[OrderService, Depends(get_order_service)],
    status: Annotated[OrderStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedOrders:
    return service.list_orders(user=user, status=status, limit=limit, offset=offset)


# list specified-id order with snapshot items
@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderResponse:
    return service.get_order(order_id=order_id, user_id=user.id)


# cancel specified-id order change status from pending to cancelled
@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderResponse:
    return service.cancel_order(order_id=order_id, user_id=user.id)
