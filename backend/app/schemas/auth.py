from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: EmailStr
    is_email_verified: bool
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MessageResponse(BaseModel):
    message: str
