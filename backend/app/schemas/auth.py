"""Authentication schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    username: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=128)


class PasswordResetRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(..., min_length=6, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=6, max_length=256)


class UserSummary(BaseModel):
    id: str
    email: str
    username: str
    role: str
    subscription_plan: str
    email_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    auth_provider: str
    user: UserSummary
    verification_notice: Optional[str] = None


class OAuthExchangeRequest(BaseModel):
    code: str = Field(..., min_length=1)
    code_verifier: Optional[str] = None


