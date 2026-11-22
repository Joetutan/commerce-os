from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.configs.auth_security import security
from app.configs.db_connection import get_db
from app.models.user_model import User, UserRole
from app.repository.user_repository import UserRepository

# Declares the bearer scheme in OpenAPI and points Swagger at the login route.
oauth2_schema = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_user_repository(db: Annotated[Session, Depends(get_db)]) -> UserRepository:
    """Build a `UserRepository` for the request-scoped session."""
    return UserRepository(db)


def get_current_user(
    token: Annotated[str, Depends(oauth2_schema)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Resolve the bearer token to the authenticated `User`.

    Raises:
        HTTPException: 401 when the token is missing or invalid, its `sub` is
            not a UUID, or the user no longer exists. Every case uses the same
            message and the `WWW-Authenticate: Bearer` header.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user_id = security().verify_access_token(token)

    if user_id is None:
        raise credentials_exception

    try:
        user_id = UUID(user_id)
    except (ValueError, TypeError) as exc:
        raise credentials_exception from exc

    repository = UserRepository(db)

    user = repository.get_by_id(user_id)

    if user is None:
        raise credentials_exception

    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required"
        )
    return user
