import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from test_postgres import postgres as postgres

from app.config import Settings
from app.main import create_app
from app.models import PitchScenario, PitchSession
from app.pitch_seed import initialize_scenario
from app.security import token_digest

pytestmark = pytest.mark.integration
ACCESS = "test-pitch"
RESET = "test-only-presenter-key-9876543210"


@pytest.fixture
def pitch(postgres):
    engine, base = postgres
    scenario_id = f"test-pitch-{uuid.uuid4().hex}"
    settings = Settings(
        _env_file=None,
        pitch_mode=True,
        database_url=base.database_url,
        pitch_access_key=ACCESS,
        pitch_reset_key=RESET,
        pitch_scenario_id=scenario_id,
    )
    assert initialize_scenario(engine, scenario_id)
    assert not initialize_scenario(engine, scenario_id)
    try:
        yield engine, settings
    finally:
        with engine.begin() as connection:
            connection.execute(delete(PitchScenario).where(PitchScenario.id == scenario_id))


def enter(client):
    response = client.post("/api/v1/pitch/login", json={"access_key": ACCESS})
    assert response.status_code == 200
    token = response.json()["access_token"]
    context = client.get(
        "/api/v1/demo/context", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert context["storage"] == "postgresql"
    return token, {
        "Authorization": f"Bearer {token}",
        "X-Demo-Actor": "empresa",
        "X-Pitch-Generation": context["scenario_generation"],
    }


def test_pitch_persists_across_app_instances_and_sessions_are_hashed(pitch):
    engine, settings = pitch
    with TestClient(create_app(settings), client=("192.0.2.5", 50000)) as client:
        assert client.get("/health/ready").json() == {"status": "pitch", "storage": "postgresql"}
        token, headers = enter(client)
        before = client.get("/api/v1/demo/company/orders", headers=headers).json()
        received = next(o for o in before if o["status"] == "recibido")
        response = client.post(
            f"/api/v1/demo/company/orders/{received['code']}/actions",
            headers=headers,
            json={"expected_revision": received["revision"], "action": "confirm"},
        )
        assert response.status_code == 200
        with engine.connect() as connection:
            stored = connection.scalar(
                select(PitchSession.token_hash).where(
                    PitchSession.scenario_id == settings.pitch_scenario_id
                )
            )
            assert stored == token_digest(token) and stored != token
    with TestClient(create_app(settings), client=("192.0.2.5", 50000)) as other:
        current = other.get("/api/v1/demo/company/orders", headers=headers).json()
        assert next(o for o in current if o["code"] == received["code"]) == response.json()


def test_reset_restores_only_own_scenario_and_rejects_stale_headers(pitch):
    engine, settings = pitch
    another_id = f"test-pitch-{uuid.uuid4().hex}"
    initialize_scenario(engine, another_id)
    try:
        with engine.connect() as connection:
            untouched = (
                connection.execute(select(PitchScenario).where(PitchScenario.id == another_id))
                .mappings()
                .one()
            )
        with TestClient(create_app(settings)) as client:
            _, headers = enter(client)
            original = client.get("/api/v1/demo/company/orders", headers=headers).json()
            body = {
                "reset_key": RESET,
                "expected_generation": headers["X-Pitch-Generation"],
                "confirmation": "REINICIAR",
            }
            assert (
                client.post(
                    "/api/v1/pitch/reset", headers=headers, json={**body, "reset_key": "wrong"}
                ).status_code
                == 403
            )
            result = client.post("/api/v1/pitch/reset", headers=headers, json=body)
            assert result.status_code == 200
            assert client.post("/api/v1/pitch/reset", headers=headers, json=body).status_code == 409
            current = client.get("/api/v1/demo/company/orders", headers=headers).json()
            assert len(current) == len(original) == 6
            assert {o["code"] for o in current}.isdisjoint(o["code"] for o in original)
            received = next(o for o in current if o["status"] == "recibido")
            path = f"/api/v1/demo/company/orders/{received['code']}/actions"
            change = {"expected_revision": received["revision"], "action": "confirm"}
            assert client.post(path, headers=headers, json=change).status_code == 409
            fresh = {**headers, "X-Pitch-Generation": result.json()["scenario_generation"]}
            assert client.post(path, headers=fresh, json=change).status_code == 200
        with engine.connect() as connection:
            assert (
                connection.execute(select(PitchScenario).where(PitchScenario.id == another_id))
                .mappings()
                .one()
                == untouched
            )
    finally:
        with engine.begin() as connection:
            connection.execute(delete(PitchScenario).where(PitchScenario.id == another_id))


def test_concurrent_instances_do_not_overwrite_each_other(pitch):
    _, settings = pitch
    with TestClient(create_app(settings)) as first, TestClient(create_app(settings)) as second:
        _, headers = enter(first)
        received = next(
            o
            for o in first.get("/api/v1/demo/company/orders", headers=headers).json()
            if o["status"] == "recibido"
        )
        path = f"/api/v1/demo/company/orders/{received['code']}/actions"
        body = {"expected_revision": received["revision"], "action": "confirm"}
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(
                executor.map(
                    lambda client: client.post(path, headers=headers, json=body), [first, second]
                )
            )
        assert sorted(r.status_code for r in responses) == [200, 409]


def test_pitch_sessions_expire_and_logout_revokes(pitch):
    engine, settings = pitch
    with TestClient(create_app(settings)) as client:
        token, headers = enter(client)
        assert client.post("/api/v1/pitch/logout", headers=headers).status_code == 204
        assert client.get("/api/v1/demo/context", headers=headers).status_code == 401
        token, headers = enter(client)
        with engine.begin() as connection:
            connection.execute(
                update(PitchSession)
                .where(PitchSession.token_hash == token_digest(token))
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        assert client.get("/api/v1/demo/context", headers=headers).status_code == 401
