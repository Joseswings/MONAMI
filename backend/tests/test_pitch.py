import copy
import json
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.demo import ACTORS, CompanyAction, OrderInput, OrderStatus
from app.main import create_app
from app.models import SCHEMA_REVISION
from app.pitch_seed import prepared_scenario
from app.pitch_state import PersistentDemoStore, dump_store, load_store, request_generation
from app.security import token_digest

RESET = "test-only-presenter-key-9876543210"
URL = "postgresql+psycopg://user:password@db.test/db?sslmode=require"


def pitch_settings(**changes):
    return Settings(
        _env_file=None,
        pitch_mode=True,
        database_url=URL,
        pitch_reset_key=RESET,
        **changes,
    )


def test_prepared_scenario_covers_pitch_without_real_contacts():
    store = prepared_scenario()
    orders = store.list_company()
    assert len(orders) == 6
    assert {order.status for order in orders} == {
        OrderStatus.RECEIVED,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.IN_TRANSIT,
        OrderStatus.DELIVERED,
    }
    assert all(order.contact_email.endswith(".test") for order in orders)
    assert len(store.list_for("cliente-1")) == len(store.list_for("cliente-2")) == 3
    trip = store.driver_trip(ACTORS[3])
    assert trip.status == "en_camino" and trip.progress_percent == 25
    assert len(trip.stops) == 2
    assert store.driver_trip(ACTORS[4]) is None
    ready = store.third_party_snapshot().candidates[0]
    assert ready.order.items[0].quantity == 61 and ready.compatible_trucks == []


def test_snapshot_roundtrip_keeps_history_dates_and_idempotency():
    original = prepared_scenario()
    payload = dump_store(original)
    encoded = json.dumps(payload)
    restored = load_store(json.loads(encoded))
    assert dump_store(restored) == payload
    first = original.get_company(next(iter(original._orders)))
    repeated, created = restored.create(
        ACTORS[0],
        OrderInput(**first.model_dump(include=set(OrderInput.model_fields))),
        "pitch-prepared-order-1",
    )
    assert not created and repeated.id == first.id
    assert original.tracking(first.code, ACTORS[0]) == restored.tracking(first.code, ACTORS[0])
    restored._orders[first.code].history.clear()
    assert original._orders[first.code].history


def test_snapshot_after_incident_and_delivery_restores_operational_rules():
    from app.demo_deliveries import DeliveryInput
    from app.demo_incidents import IncidentInput, ResolutionInput

    store = prepared_scenario()
    trip = store.driver_trip(ACTORS[3])
    blocked = store.report_incident(
        trip.id,
        IncidentInput(expected_revision=trip.revision, kind="bloqueo", reason="Prueba"),
        ACTORS[3],
    )
    store = load_store(dump_store(store))
    resumed = store.resolve_incident(
        trip.id,
        blocked.active_incident_id,
        ResolutionInput(
            expected_revision=blocked.revision,
            decision="alternativa",
            delay_minutes=15,
            resolution_note="Desvío de prueba",
        ),
        ACTORS[2],
    )
    delivered = store.deliver_order(
        trip.id,
        resumed.stops[0].code,
        DeliveryInput(
            expected_revision=resumed.revision,
            expected_order_revision=resumed.stops[0].order_revision,
        ),
        ACTORS[3],
    )
    restored = load_store(dump_store(store))
    assert restored.driver_trip(ACTORS[3]) == delivered
    assert restored.get_company(delivered.stops[0].code).status == OrderStatus.DELIVERED


def test_new_prepared_scenario_has_new_identity_but_same_roles_and_stages():
    first, second = prepared_scenario(), prepared_scenario()
    assert set(first._orders).isdisjoint(second._orders)
    assert [order.status for order in first.list_company()] == [
        order.status for order in second.list_company()
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"demo_mode": True},
        {"pitch_reset_key": None},
        {"pitch_reset_key": "short"},
        {"pitch_reset_key": "r" * 23},
        {"pitch_reset_key": "r" * 257},
        {"pitch_reset_key": "REPLACE_WITH_RANDOM_PRESENTER_KEY"},
        {"database_url": None},
        {"pitch_scenario_id": "../other"},
    ],
)
def test_pitch_configuration_is_explicit_and_secret_errors_are_sanitized(change):
    values = dict(pitch_mode=True, database_url=URL, pitch_reset_key=RESET)
    values.update(change)
    with pytest.raises(ValidationError) as failure:
        Settings(_env_file=None, **values)
    assert RESET not in str(failure.value) and "user:password" not in str(failure.value)


@pytest.mark.parametrize("reset_key", ["r" * 24, "r" * 256])
def test_public_pitch_only_requires_presenter_key(reset_key, monkeypatch):
    # Una variable antigua en el proveedor no debe impedir el acceso público.
    monkeypatch.setenv("PITCH_ACCESS_KEY", "obsolete")
    settings = Settings(
        _env_file=None,
        pitch_mode=True,
        database_url=URL,
        pitch_reset_key=reset_key,
    )
    assert settings.pitch_reset_key.get_secret_value() == reset_key


def fake_store():
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    generation = uuid.uuid4()
    row = {
        "id": "monami-pitch",
        "generation": generation,
        "payload": dump_store(prepared_scenario()),
    }
    connection.execute.return_value.mappings.return_value.first.return_value = row
    return PersistentDemoStore(engine, "monami-pitch"), connection, row


def test_persistent_proxy_rejects_stale_generation_before_mutation():
    store, connection, row = fake_store()
    received = next(
        o for o in load_store(row["payload"]).list_company() if o.status == OrderStatus.RECEIVED
    )
    token = request_generation.set(str(uuid.uuid4()))
    try:
        with pytest.raises(HTTPException) as failure:
            store.act(
                received.code,
                ACTORS[2],
                CompanyAction(expected_revision=received.revision, action="confirm"),
            )
        assert failure.value.status_code == 409
    finally:
        request_generation.reset(token)
    assert not any(
        getattr(args[0], "is_update", False) for args, kwargs in connection.execute.call_args_list
    )


def test_persistent_proxy_only_saves_valid_mutations_under_row_lock():
    store, connection, row = fake_store()
    original = copy.deepcopy(row["payload"])
    received = next(
        o for o in load_store(row["payload"]).list_company() if o.status == OrderStatus.RECEIVED
    )
    token = request_generation.set(str(row["generation"]))
    try:
        result = store.act(
            received.code,
            ACTORS[2],
            CompanyAction(expected_revision=received.revision, action="confirm"),
        )
    finally:
        request_generation.reset(token)
    assert result.status == OrderStatus.CONFIRMED and row["payload"] == original
    statements = [args[0] for args, kwargs in connection.execute.call_args_list]
    assert any("FOR UPDATE" in str(statement) for statement in statements)
    saved = next(statement for statement in statements if getattr(statement, "is_update", False))
    assert "confirmado" in str(saved.compile().params["payload"])


def test_unknown_snapshot_version_and_missing_scenario_are_controlled():
    payload = dump_store(prepared_scenario())
    payload["version"] = 2
    with pytest.raises(HTTPException) as failure:
        load_store(payload)
    assert failure.value.status_code == 503
    store, connection, _ = fake_store()
    connection.execute.return_value.mappings.return_value.first.return_value = None
    with pytest.raises(HTTPException) as missing:
        store.list_company()
    assert missing.value.status_code == 503
    with pytest.raises(AttributeError):
        _ = store._orders


def test_pitch_gate_opens_remote_demo_only_after_access_and_sanitizes_database_errors(monkeypatch):
    engine = MagicMock()
    monkeypatch.setattr("app.main.build_engine", lambda _: engine)
    with TestClient(create_app(pitch_settings()), client=("192.0.2.5", 50000)) as client:
        assert client.get("/api/v1/demo/context").status_code == 401
        assert (
            client.get(
                "/api/v1/demo/company/orders", headers={"X-Demo-Actor": "empresa"}
            ).status_code
            == 401
        )
        engine.connect.return_value.__enter__.side_effect = OperationalError(
            "secret", {}, Exception(URL)
        )
        failed = client.get(
            "/api/v1/demo/context", headers={"Authorization": "Bearer opaque-token"}
        )
        assert failed.status_code == 503 and "password" not in failed.text


def test_public_pitch_login_sanitizes_database_errors(monkeypatch):
    engine = MagicMock()
    monkeypatch.setattr("app.main.build_engine", lambda _: engine)
    engine.begin.return_value.__enter__.side_effect = OperationalError("secret", {}, Exception(URL))
    with TestClient(create_app(pitch_settings())) as client:
        response = client.post("/api/v1/pitch/login")
        assert response.status_code == 503 and "password" not in response.text


def test_pitch_login_creates_hashed_session_without_key_or_body(monkeypatch):
    store, connection, _ = fake_store()
    connection.scalar.return_value = SCHEMA_REVISION
    monkeypatch.setattr("app.main.build_engine", lambda _: store.engine)
    with TestClient(create_app(pitch_settings())) as client:
        contract = client.get("/openapi.json").json()["paths"]["/api/v1/pitch/login"]["post"]
        assert "requestBody" not in contract
        response = client.post("/api/v1/pitch/login")
        assert response.status_code == 200
        assert response.json()["access_token"] and response.json()["expires_at"]
        token = response.json()["access_token"]
        inserted = next(
            args[0]
            for args, _ in connection.execute.call_args_list
            if getattr(args[0], "is_insert", False)
        )
        assert inserted.compile().params["token_hash"] == token_digest(token)
        assert inserted.compile().params["token_hash"] != token


def test_public_access_does_not_allow_reset_without_presenter_key(monkeypatch):
    engine = MagicMock()
    monkeypatch.setattr("app.main.build_engine", lambda _: engine)
    with TestClient(create_app(pitch_settings())) as client:
        body = {"expected_generation": str(uuid.uuid4()), "confirmation": "REINICIAR"}
        headers = {"Authorization": "Bearer public-session"}
        assert client.post("/api/v1/pitch/reset", headers=headers, json=body).status_code == 422
        response = client.post(
            "/api/v1/pitch/reset", headers=headers, json={**body, "reset_key": "wrong"}
        )
        assert response.status_code == 403
        engine.begin.assert_not_called()


def test_pitch_endpoints_absent_from_local_and_identity_modes():
    for settings in (Settings(_env_file=None, demo_mode=True), Settings(_env_file=None)):
        with TestClient(create_app(settings), client=("127.0.0.1", 50000)) as client:
            assert client.post("/api/v1/pitch/reset", json={}).status_code == 404


def test_pitch_api_passes_generation_to_sync_store_without_cross_request_leaks(monkeypatch):
    store, connection, row = fake_store()
    monkeypatch.setattr("app.main.build_engine", lambda _: store.engine)
    monkeypatch.setattr("app.pitch_access.require_pitch_session", lambda request: "test-session")
    received = next(
        o for o in load_store(row["payload"]).list_company() if o.status == OrderStatus.RECEIVED
    )
    with TestClient(create_app(pitch_settings()), client=("192.0.2.5", 50000)) as client:
        path = f"/api/v1/demo/company/orders/{received.code}/actions"
        body = {"expected_revision": received.revision, "action": "confirm"}
        valid = {"X-Demo-Actor": "empresa", "X-Pitch-Generation": str(row["generation"])}
        assert client.post(path, headers=valid, json=body).status_code == 200
        assert client.post(path, headers={"X-Demo-Actor": "empresa"}, json=body).status_code == 409
        assert request_generation.get() is None


def test_pitch_order_limit_preserves_idempotent_retries(monkeypatch):
    monkeypatch.setattr("app.pitch_state.MAX_PITCH_ORDERS", 6)
    store, connection, row = fake_store()
    first = next(iter(load_store(row["payload"])._orders.values()))
    data = OrderInput(**first.model_dump(include=set(OrderInput.model_fields)))
    generation = request_generation.set(str(row["generation"]))
    try:
        repeated, created = store.create(ACTORS[0], data, "pitch-prepared-order-1")
        assert not created and repeated.id == first.id
        with pytest.raises(HTTPException) as failure:
            store.create(ACTORS[0], data, "new-order-exceeds-pitch-limit")
        assert failure.value.status_code == 409
    finally:
        request_generation.reset(generation)


def test_pitch_payload_limit_does_not_write_partial_state(monkeypatch):
    monkeypatch.setattr("app.pitch_state.MAX_PAYLOAD_BYTES", 1)
    store, connection, row = fake_store()
    received = next(
        o for o in load_store(row["payload"]).list_company() if o.status == OrderStatus.RECEIVED
    )
    generation = request_generation.set(str(row["generation"]))
    try:
        with pytest.raises(HTTPException) as failure:
            store.act(
                received.code,
                ACTORS[2],
                CompanyAction(expected_revision=received.revision, action="confirm"),
            )
        assert failure.value.status_code == 409
    finally:
        request_generation.reset(generation)
    assert not any(
        getattr(args[0], "is_update", False) for args, kwargs in connection.execute.call_args_list
    )
