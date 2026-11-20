from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_model import User


class UserRepository:
    """Persistence operations for `User` rows.

    Wraps a SQLAlchemy `Session`; callers own the session lifecycle.
    """

    def __init__(self, db: Session) -> None:
        """Store the session used for all queries and writes."""
        self.db = db

    def create(self, username: str, email: str, password_hash: str) -> User:
        """Insert a user, commit, and return the refreshed row.

        Raises:
            IntegrityError: if `email` already exists.
        """
        user = User(username=username, email=email, password_hash=password_hash)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_by_email(self, email: str) -> User | None:
        """Return the user with `email`, or `None` if no row matches.

        The comparison is case-sensitive.
        """
        statement = select(User).where(User.email == email)
        return self.db.scalar(statement)

    def get_by_id(self, user_id: UUID) -> User | None:
        """Return the user with `user_id`, or `None` if no row matches."""
        statement = select(User).where(User.id == user_id)
        return self.db.scalar(statement)
