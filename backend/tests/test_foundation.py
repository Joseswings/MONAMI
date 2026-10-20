import uuid
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import OperationalError

from app.api import Principal, current_principal
from app.config import Settings
from app.database import get_db
from app.main import create_app
from app.models import AuthSession, Organization, Role, User
from app.security import create_token, hash_password, token_digest, verify_password


@pytest.fixture
def client():
    app = create_app(Settings(_env_file=None, database_url=None))
    with TestClient(app) as test_client:
        yield test_client


def test_live_and_openapi_without_database(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) == {
        "/health/live",
        "/health/ready",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/me",
        "/api/v1/company",
    }
    assert "HTTPBearer" in client.get("/openapi.json").json()["components"]["securitySchemes"]


def test_missing_database_is_not_ready(client):
    assert client.get("/health/ready").status_code == 503
    result = client.post("/api/v1/auth/login", json={"email": "a@b.test", "password": "example"})
    assert result.status_code == 503


def test_database_error_is_sanitized(client):
    def broken_db():
        raise OperationalError("SELECT secret", {}, Exception("postgresql://private-password"))

    client.app.dependency_overrides[get_db] = broken_db
    result = client.get("/health/ready")
    assert result.status_code == 503
    assert result.json() == {"detail": "Servicio de datos no disponible"}
    assert "private-password" not in result.text


def test_outdated_schema_is_not_ready(client):
    db = MagicMock()
    db.scalar.return_value = "older-revision"
    client.app.dependency_overrides[get_db] = lambda: db
    assert client.get("/health/ready").status_code == 503


def test_validation_does_not_echo_password(client):
    client.app.dependency_overrides[get_db] = lambda: MagicMock()
    result = client.post("/api/v1/auth/login", json={"email": "x", "password": "private-input"})
    assert result.status_code == 422
    assert "private-input" not in result.text


@pytest.mark.parametrize("role", list(Role))
def test_identity_and_company_role_gate(client, role):
    organization = Organization(id=uuid.uuid4(), name="Organization A")
    principal = Principal(
        User(
            id=uuid.uuid4(),
            organization_id=organization.id,
            name="Demo",
            email="demo@a.test",
            role=role.value,
            password_hash="not-exposed",
            is_active=True,
        ),
        organization,
        AuthSession(
            token_hash="not-exposed",
            user_id=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
    )
    client.app.dependency_overrides[current_principal] = lambda: principal
    result = client.get("/api/v1/me")
    assert result.status_code == 200
    assert result.json()["organization"]["id"] == str(organization.id)
    assert "password_hash" not in result.text
    assert "token_hash" not in result.text
    company = client.get("/api/v1/company")
    assert company.status_code == (200 if role == Role.COMPANY else 403)


def test_missing_invalid_and_revoked_tokens(client):
    db = MagicMock()
    db.execute.return_value.first.return_value = None
    client.app.dependency_overrides[get_db] = lambda: db
    for headers in ({}, {"Authorization": "Basic invalid"}, {"Authorization": "Bearer revoked"}):
        result = client.get("/api/v1/me", headers=headers)
        assert result.status_code == 401
        assert result.headers["www-authenticate"] == "Bearer"


def test_cors_only_allows_configured_origin(client):
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    }
    allowed = client.options("/api/v1/auth/login", headers=headers)
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    denied = client.options(
        "/api/v1/auth/login", headers={**headers, "Origin": "https://other.test"}
    )
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


def test_sensitive_responses_are_not_cached(client):
    assert client.get("/health/live").headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///local.db",
        "postgresql://user:password@db.test/db?sslmode=require",
        "postgresql+psycopg://user:password@db.test/db",
        "postgresql+psycopg://user:password@db.test/db?sslmode=disable",
        "postgresql+psycopg://user@db.test/db?sslmode=require",
    ],
)
def test_database_configuration_requires_psycopg_and_tls(url):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_url=SecretStr(url))
    assert "user:password" not in str(error.value)


def test_configuration_accepts_encrypted_postgres():
    settings = Settings(
        _env_file=None,
        database_url=SecretStr("postgresql+psycopg://user:password@db.test/db?sslmode=require"),
    )
    assert settings.database_url is not None
    assert "password" not in repr(settings)


@pytest.mark.parametrize("origins", [["*"], ["https://web.test/path"], ["file://local"]])
def test_cors_rejects_ambiguous_origins(origins):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=origins)


def test_password_hashing_and_opaque_tokens():
    password = "temporary-test-value"
    hashed = hash_password(password)
    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed)
    assert not verify_password("incorrect", hashed)
    assert not verify_password(password, None)
    assert not verify_password(password, "corrupt-hash")
    token, expiry = create_token(60)
    other_token, _ = create_token(60)
    assert token != other_token
    assert token_digest(token) != token
    assert len(token_digest(token)) == 64
    assert expiry > datetime.now(UTC) + timedelta(minutes=59)


def test_initial_migration_generates_postgres_sql(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://user:password@db.test/test?sslmode=require"
    )
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE SCHEMA monami" in sql
    for table in ("organizations", "users", "sessions"):
        assert f"CREATE TABLE monami.{table}" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "0001_identity" in sql
    assert "password@db.test" not in sql
