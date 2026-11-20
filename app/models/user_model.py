from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.configs.db_connection import Base


class UserRole(StrEnum):
    """Account roles allowed by the `ck_users_role` check constraint."""

    CUSTOMER = "customer"
    ADMIN = "admin"


class User(Base):
    """Registered account.

    Only the password hash is stored. `role` defaults to `customer` in both
    Python and the database, and `created_at` is filled in by the server.
    """

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )

    username: Mapped[str] = mapped_column(String(255), nullable=False)

    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="ck_users_role",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            length=20,
        ),
        nullable=False,
        default=UserRole.CUSTOMER,
        server_default=UserRole.CUSTOMER.value,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
