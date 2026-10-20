"""Carga explícita e idempotente. Nunca se ejecuta al iniciar FastAPI."""

import uuid

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import build_engine
from app.models import Organization, Role, User
from app.security import hash_password

DEMO_ORGANIZATION_ID = uuid.UUID("bda11341-a48a-4604-9e09-b92651aa7895")


class DemoPasswords(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="DEMO_", extra="ignore", hide_input_in_errors=True
    )
    client_password: SecretStr = Field(min_length=12, max_length=1024)
    company_password: SecretStr = Field(min_length=12, max_length=1024)
    driver_password: SecretStr = Field(min_length=12, max_length=1024)


def seed_demo(engine: Engine, passwords: DemoPasswords) -> None:
    accounts = (
        ("cliente@monami.test", "Cliente demo", Role.CLIENT, passwords.client_password),
        ("empresa@monami.test", "Empresa demo", Role.COMPANY, passwords.company_password),
        ("conductor@monami.test", "Conductor demo", Role.DRIVER, passwords.driver_password),
    )
    with Session(engine) as db, db.begin():
        if db.get(Organization, DEMO_ORGANIZATION_ID) is None:
            db.add(Organization(id=DEMO_ORGANIZATION_ID, name="Monami Demo"))
            db.flush()
        for email, name, role, password in accounts:
            existing = db.scalar(select(User).where(User.email == email))
            if existing is not None:
                if existing.organization_id != DEMO_ORGANIZATION_ID or existing.role != role.value:
                    raise RuntimeError("Una cuenta demo existente tiene otra organización o rol")
                continue
            db.add(
                User(
                    organization_id=DEMO_ORGANIZATION_ID,
                    email=email,
                    name=name,
                    role=role.value,
                    password_hash=hash_password(password.get_secret_value()),
                )
            )


def main() -> None:
    try:
        settings = Settings()
        passwords = DemoPasswords()
    except ValidationError:
        raise SystemExit(
            "Configuración inválida: revisar URL y las tres contraseñas DEMO_*"
        ) from None
    if settings.database_url is None:
        raise SystemExit("Falta DATABASE_URL")
    engine = build_engine(settings.database_url)
    try:
        seed_demo(engine, passwords)
    except (SQLAlchemyError, RuntimeError):
        raise SystemExit(
            "No se pudo cargar la demo; revisar migración y cuentas existentes"
        ) from None
    finally:
        engine.dispose()
    print("Cuentas demo disponibles. No se modificaron contraseñas existentes.")


if __name__ == "__main__":
    main()
