"""Pruebas reales de PostgreSQL; no se sustituye por SQLite.

Requieren una base separada y confirmación explícita. Solo limpian sus propias filas.
"""

import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import build_engine
from app.main import create_app
from app.models import SCHEMA_REVISION, AuthSession, Organization, Role, User
from app.security import hash_password, token_digest
from app.seed import DEMO_ORGANIZATION_ID, DemoPasswords, seed_demo

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres():
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("Falta TEST_DATABASE_URL: PostgreSQL de pruebas separado")
    if os.environ.get("MONAMI_TEST_DATABASE_CONFIRMED") != "true":
        pytest.fail("Configurar MONAMI_TEST_DATABASE_CONFIRMED=true para la base separada")
    settings = Settings(_env_file=None, database_url=SecretStr(test_url))
    production = Settings().database_url
    if production:

        def destination(value):
            parsed = make_url(value)
            return parsed.host, parsed.port or 5432, parsed.database

        if destination(test_url) == destination(production.get_secret_value()):
            pytest.fail("TEST_DATABASE_URL no puede apuntar al destino de DATABASE_URL")
    # Alembic recibe SOLO la URL de prueba. No se imprimen valores de conexión.
    previous = {key: os.environ.get(key) for key in ("DATABASE_URL", "MIGRATION_DATABASE_URL")}
    try:
        os.environ["DATABASE_URL"] = test_url
        os.environ["MIGRATION_DATABASE_URL"] = test_url
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(config, "head")
        command.upgrade(config, "head")
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    engine = build_engine(settings.database_url)
    yield engine, settings
    engine.dispose()


@pytest.fixture
def accounts(postgres):
    engine, settings = postgres
    password = secrets.token_urlsafe(24)
    organizations = [uuid.uuid4(), uuid.uuid4()]
    users = []
    with Session(engine) as db, db.begin():
        for index, organization_id in enumerate(organizations):
            db.add(Organization(id=organization_id, name=f"Test organization {index}"))
        db.flush()
        for index, role in enumerate([Role.CLIENT, Role.COMPANY, Role.DRIVER, Role.COMPANY]):
            organization_id = organizations[0 if index < 3 else 1]
            user = User(
                id=uuid.uuid4(),
                organization_id=organization_id,
                email=f"{uuid.uuid4()}@monami.test",
                name=f"Test {role.value}",
                role=role.value,
                password_hash=hash_password(password),
                is_active=True,
            )
            db.add(user)
            users.append({"id": user.id, "email": user.email, "organization_id": organization_id})
    with TestClient(create_app(settings)) as client:
        yield engine, client, users, password
    with Session(engine) as db, db.begin():
        db.execute(delete(User).where(User.organization_id.in_(organizations)))
        db.execute(delete(Organization).where(Organization.id.in_(organizations)))


def login(client, account, password):
    response = client.post(
        "/api/v1/auth/login", json={"email": account["email"], "password": password}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_migration_and_readiness(postgres):
    engine, settings = postgres
    with Session(engine) as db:
        assert (
            db.scalar(text("SELECT version_num FROM public.monami_schema_version"))
            == SCHEMA_REVISION
        )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").json() == {"status": "ready"}


def test_login_me_logout_and_token_storage(accounts):
    engine, client, users, password = accounts
    token = login(client, users[0], password)
    headers = {"Authorization": f"Bearer {token}"}
    identity = client.get("/api/v1/me", headers=headers).json()
    assert identity["id"] == str(users[0]["id"])
    with Session(engine) as db:
        stored = db.scalar(select(AuthSession).where(AuthSession.user_id == users[0]["id"]))
        assert stored.token_hash == token_digest(token)
        assert stored.token_hash != token
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/me", headers=headers).status_code == 401


def test_wrong_credentials_do_not_issue_session(accounts):
    engine, client, users, _ = accounts
    for email in (users[0]["email"], "missing@monami.test"):
        response = client.post("/api/v1/auth/login", json={"email": email, "password": "incorrect"})
        assert response.status_code == 401
    with Session(engine) as db:
        assert db.scalar(select(AuthSession).where(AuthSession.user_id == users[0]["id"])) is None


def test_company_is_scoped_to_authenticated_organization(accounts):
    _, client, users, password = accounts
    for index in (1, 3):
        token = login(client, users[index], password)
        # Un parámetro ajeno no altera el ámbito, que se obtiene de la sesión.
        other = users[3 if index == 1 else 1]
        result = client.get(
            f"/api/v1/company?organization_id={other['organization_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert result.status_code == 200
        assert result.json()["id"] == str(users[index]["organization_id"])
    for index in (0, 2):
        token = login(client, users[index], password)
        assert (
            client.get("/api/v1/company", headers={"Authorization": f"Bearer {token}"}).status_code
            == 403
        )


def test_expired_and_disabled_sessions(accounts):
    engine, client, users, password = accounts
    token = login(client, users[0], password)
    with Session(engine) as db, db.begin():
        stored = db.get(AuthSession, token_digest(token))
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    token = login(client, users[0], password)
    with Session(engine) as db, db.begin():
        db.get(User, users[0]["id"]).is_active = False
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": users[0]["email"], "password": password}
        ).status_code
        == 401
    )


def test_seed_is_explicit_and_idempotent(postgres):
    engine, settings = postgres
    with Session(engine) as db:
        if db.get(Organization, DEMO_ORGANIZATION_ID) is not None:
            pytest.skip("La organización demo ya existe; no se alteran sus cuentas")
    password = secrets.token_urlsafe(24)
    passwords = DemoPasswords(
        _env_file=None,
        client_password=password,
        company_password=password,
        driver_password=password,
    )
    try:
        seed_demo(engine, passwords)
        with Session(engine) as db:
            before = {
                u.email: u.password_hash
                for u in db.scalars(
                    select(User).where(User.organization_id == DEMO_ORGANIZATION_ID)
                )
            }
        seed_demo(engine, passwords)
        with Session(engine) as db:
            after = {
                u.email: u.password_hash
                for u in db.scalars(
                    select(User).where(User.organization_id == DEMO_ORGANIZATION_ID)
                )
            }
        assert len(after) == 3
        assert before == after
        with TestClient(create_app(settings)) as client:
            for email in after:
                token = login(client, {"email": email}, password)
                assert (
                    client.post(
                        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"}
                    ).status_code
                    == 204
                )
    finally:
        with Session(engine) as db, db.begin():
            db.execute(delete(User).where(User.organization_id == DEMO_ORGANIZATION_ID))
            db.execute(delete(Organization).where(Organization.id == DEMO_ORGANIZATION_ID))
