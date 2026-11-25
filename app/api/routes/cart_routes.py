from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.configs.db_connection import get_db
from app.models.user_model import User
from app.repository.cart_repository import CartRepository
from app.schemas.cart_schema import (
    CartItemCreate,
    CartItemUpdate,
    CartResponse,
)
from app.service.cart_service import CartService
from app.utils.auth_dependencies import get_current_user

router = APIRouter(prefix="/api/v1/cart", tags=["cart"])


def get_cart_service(db: Annotated[Session, Depends(get_db)]) -> CartService:
    return CartService(CartRepository(db))


@router.get(
    "",
    response_model=CartResponse,
)
def get_cart(
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartResponse:
    cart = service.get_cart(user_id=user.id)
    return service.cart_to_response(cart=cart)


@router.post(
    "/items",
    response_model=CartResponse,
)
def add_item(
    data: CartItemCreate,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartResponse:
    return service.add_item(user_id=user.id, data=data)


@router.patch(
    "/items/{item_id}",
    response_model=CartResponse,
)
def update_item(
    item_id: UUID,
    data: CartItemUpdate,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartResponse:
    return service.update_item(user_id=user.id, item_id=item_id, data=data)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> None:
    service.delete_item(item_id=item_id, user_id=user.id)
