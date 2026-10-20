from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.models import Role


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class LoginOutput(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class OrganizationOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str


class IdentityOutput(BaseModel):
    id: UUID
    name: str
    email: str
    role: Role
    organization: OrganizationOutput


class HealthOutput(BaseModel):
    status: str


class ErrorOutput(BaseModel):
    detail: str
