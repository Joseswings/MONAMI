from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def validate_database_url(value: SecretStr | None) -> SecretStr | None:
    if value is None:
        return None
    try:
        url = make_url(value.get_secret_value())
    except ArgumentError:
        raise ValueError("DATABASE_URL debe ser una URL PostgreSQL válida") from None
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Usar el controlador postgresql+psycopg")
    if url.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("La conexión PostgreSQL requiere sslmode=require o verificación superior")
    if not url.host or not url.username or not url.password or not url.database:
        raise ValueError("La conexión requiere host, usuario, contraseña y base")
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"), extra="ignore", hide_input_in_errors=True
    )

    demo_mode: bool = False
    pitch_mode: bool = False
    pitch_access_key: SecretStr | None = None
    pitch_reset_key: SecretStr | None = None
    pitch_scenario_id: str = Field(default="monami-pitch", pattern=r"^[a-z0-9-]{1,64}$")
    database_url: SecretStr | None = None
    migration_database_url: SecretStr | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    session_ttl_minutes: int = Field(default=480, ge=1, le=1440)

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        if self.demo_mode and self.pitch_mode:
            raise ValueError("Elegir DEMO_MODE local o PITCH_MODE desplegable")
        if self.pitch_mode:
            if self.database_url is None:
                raise ValueError("PITCH_MODE requiere DATABASE_URL")
            for key in (self.pitch_access_key, self.pitch_reset_key):
                if key is None or not 24 <= len(key.get_secret_value()) <= 256:
                    raise ValueError("Las claves de pitch requieren entre 24 y 256 caracteres")
                if "REPLACE" in key.get_secret_value():
                    raise ValueError("Reemplazar las claves de ejemplo del pitch")
            if self.pitch_access_key == self.pitch_reset_key:
                raise ValueError("Usar claves distintas de acceso y reinicio")
        if not self.demo_mode:
            validate_database_url(self.database_url)
            validate_database_url(self.migration_database_url)
        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise ValueError("CORS_ORIGINS debe contener orígenes HTTP explícitos sin ruta")
        return self
