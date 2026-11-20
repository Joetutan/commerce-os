from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """Registration payload.

    `role` is intentionally absent so clients cannot self-assign one.
    """

    username: str = Field(examples=["alice"])
    email: EmailStr = Field(examples=["alice@example.com"])
    password: str = Field(examples=["correct-horse-battery-staple"])


class UserResponse(BaseModel):
    """Public user profile; never includes the password hash or role."""

    id: UUID
    username: str
    email: EmailStr
    model_config = {"from_attributes": True}
