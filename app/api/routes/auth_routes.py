from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.models.user_model import User
from app.repository.user_repository import UserRepository
from app.schemas.auth_schema import ResponseToken
from app.schemas.user_schema import UserCreate, UserResponse
from app.service.auth_service import AuthService
from app.utils.auth_dependencies import get_current_user, get_user_repository

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def get_auth_service(
    repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> AuthService:
    """Build an `AuthService` backed by the request's repository."""
    return AuthService(repository)


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
def register(
    data: UserCreate, service: Annotated[AuthService, Depends(get_auth_service)]
) -> UserResponse:
    """Create an account and return its public profile.

    Raises:
        HTTPException: 409 when the email is already registered.
    """
    user = service.register(
        username=data.username, email=data.email, password=data.password
    )
    return UserResponse(id=user.id, username=user.username, email=user.email)


@router.post("/login", response_model=ResponseToken)
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> ResponseToken:
    """Exchange OAuth2 form credentials for a bearer token.

    The form's `username` field carries the email address.

    Raises:
        HTTPException: 401 for invalid credentials.
    """
    access_token = service.login(email=form_data.username, password=form_data.password)
    return ResponseToken(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return the authenticated user's public profile."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
    )
