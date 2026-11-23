from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=12, max_length=200)
    role: str
    is_active: bool = True


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    password: str | None = Field(default=None, min_length=12, max_length=200)
    role: str | None = None
    is_active: bool | None = None


class AuthorizedAreaAssignment(BaseModel):
    area_ids: list[UUID] = []


class UserAdminRead(BaseModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool
    roles: list[str]
    authorized_area_ids: list[UUID]
