from pydantic import BaseModel, Field


class LocationVerificationRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_meters: float | None = Field(default=None, ge=0)


class LocationVerificationResponse(BaseModel):
    allowed: bool
    area_name: str | None = None
    expires_at: str | None = None
    message: str


class AuthorizedAreaRead(BaseModel):
    id: str
    name: str
    description: str | None = None
    original_filename: str | None = None
    is_active: bool


class AuthorizedAreaUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
