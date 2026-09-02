from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class PermissionRead(BaseModel):
    code: str
    name: str
    module: str


class RoleRead(BaseModel):
    code: str
    name: str
    permissions: list[PermissionRead] = []


class CurrentUserRead(BaseModel):
    id: str
    email: str
    full_name: str
    roles: list[str]
    permissions: list[str]


class LoginResponse(BaseModel):
    user: CurrentUserRead
