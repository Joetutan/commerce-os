from fastapi import HTTPException, status

from app.configs.auth_security import security
from app.models.user_model import User
from app.repository.user_repository import UserRepository


class AuthService:
    """Registration and login rules, independent of HTTP transport.

    Expected auth failures surface as `HTTPException`, so every caller gets
    the same status codes and messages.
    """

    def __init__(self, user_repository: UserRepository) -> None:
        """Store the repository used to read and create users."""
        self.user_repository = user_repository

    def get_user(self, email: str) -> User | None:
        """Return the user with `email`, or `None` if it is unknown."""
        return self.user_repository.get_by_email(email=email)

    def register(self, username: str, email: str, password: str) -> User:
        """Create a user with a hashed password.

        Raises:
            HTTPException: 409 if `email` is already registered.
        """
        existing_user = self.get_user(email)

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
            )

        password_hash = security().hash_password(password)

        return self.user_repository.create(
            username=username, email=email, password_hash=password_hash
        )

    def login(self, email: str, password: str) -> str:
        """Return a JWT access token for valid credentials.

        Unknown emails and wrong passwords produce the same 401 response so
        the API does not reveal which accounts exist.

        Raises:
            HTTPException: 401 if the credentials are invalid.
        """
        user = self.get_user(email)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Credentials"
            )

        if not security().verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Credentials"
            )

        return security().create_access_token(user.id)
