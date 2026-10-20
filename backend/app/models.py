import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "monami"
SCHEMA_REVISION = "0002_pitch"


class Base(DeclarativeBase):
    pass


class Role(enum.StrEnum):
    CLIENT = "cliente"
    COMPANY = "empresa"
    DRIVER = "conductor"


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160))


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('cliente', 'empresa', 'conductor')", name="ck_users_role"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.organizations.id"), index=True
    )
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class AuthSession(Base):
    __tablename__ = "sessions"
    __table_args__ = {"schema": SCHEMA}

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PitchScenario(Base):
    __tablename__ = "pitch_scenarios"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    generation: Mapped[uuid.UUID] = mapped_column(Uuid)
    payload: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PitchSession(Base):
    __tablename__ = "pitch_sessions"
    __table_args__ = {"schema": SCHEMA}

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.pitch_scenarios.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
