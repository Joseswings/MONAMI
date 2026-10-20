from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo import ACTORS, CompanyAction, DemoOrderStore, OrderInput
from app.main import create_app

ROOT = "/api/v1/demo"
COMPANY = {"X-Demo-Actor": "empresa"}
CUSTOMER = {"X-Demo-Actor": "cliente-1", "Idempotency-Key": "company-test-order"}
DATA = {
    "contact_name": "Ana de prueba",
    "contact_email": "ana@empresatest.test",
    "contact_phone": "5555 1234",
    "items": [{"product": "Caja", "quantity": 2}],
    "address": "Zona 10, Guatemala",
    "location": None,
    "instructions": "Llamar antes de llegar",
}


@pytest.fixture
def client():
    with TestClient(
        create_app(Settings(_env_file=None, demo_mode=True)), client=("127.0.0.1", 50001)
    ) as client:
        yield client


@pytest.fixture
def order(client):
    response = client.post(f"{ROOT}/orders", headers=CUSTOMER, json=DATA)
    assert response.status_code == 201
    return response.json()


def action(client, order, action, note=""):
    return client.post(
        f"{ROOT}/company/orders/{order['code']}/actions",
        headers=COMPANY,
        json={"action": action, "note": note, "expected_revision": order["revision"]},
    )


def schedule(client, order, **changes):
    departure = datetime.now(UTC) + timedelta(days=2)
    return client.post(
        f"{ROOT}/company/orders/{order['code']}/schedule",
        headers=COMPANY,
        json={
            "expected_revision": order["revision"],
            "scheduled_departure_at": departure.isoformat(),
            "estimated_delivery_at": (departure + timedelta(days=1)).isoformat(),
            **changes,
        },
    )


def correction(client, order, data=None, actor="cliente-1"):
    return client.post(
        f"{ROOT}/orders/{order['code']}/correction",
        headers={"X-Demo-Actor": actor},
        json={"order": data or DATA, "expected_revision": order["revision"]},
    )


def test_company_sees_both_customers_but_clients_remain_scoped(client, order):
    other = client.post(
        f"{ROOT}/orders", headers={**CUSTOMER, "X-Demo-Actor": "cliente-2"}, json=DATA
    ).json()
    company_orders = client.get(f"{ROOT}/company/orders", headers=COMPANY).json()
    assert {o["code"] for o in company_orders} == {order["code"], other["code"]}
    assert len(client.get(f"{ROOT}/orders", headers=CUSTOMER).json()) == 1
    assert (
        client.get(f"{ROOT}/company/orders/{order['code'].lower()}", headers=COMPANY).json()
        == order
    )
    assert client.get(f"{ROOT}/company/orders/MON-00000000", headers=COMPANY).status_code == 404


def test_company_progress_and_dates_are_visible_to_customer(client, order):
    assert action(client, order, "start_preparation").status_code == 409
    assert action(client, order, "mark_ready").status_code == 409
    assert schedule(client, order).status_code == 409
    confirmed = action(client, order, "confirm").json()
    assert confirmed["status"] == "confirmado"
    assert action(client, confirmed, "confirm").status_code == 409
    assert action(client, confirmed, "request_correction", "Cambiar dirección").status_code == 409
    preparing = action(client, confirmed, "start_preparation").json()
    assert preparing["status"] == "preparando"
    assert action(client, preparing, "mark_ready").status_code == 409
    dated = schedule(client, preparing).json()
    ready = action(client, dated, "mark_ready").json()
    assert ready["status"] == "listo_para_salir"
    assert ready["revision"] == 5
    assert ready["delivery_mode"] is None
    assert ready["delivered_at"] is None
    assert len(ready["history"]) == 5
    assert ready["history"][3]["scheduled_departure_at"] == dated["scheduled_departure_at"]
    assert client.get(f"{ROOT}/orders/{order['code']}", headers=CUSTOMER).json() == ready
    assert action(client, ready, "start_preparation").status_code == 409
    assert action(client, ready, "mark_ready").status_code == 409
    for forbidden in ("en_camino", "entregado", "cancel", "dispatch"):
        assert action(client, ready, forbidden).status_code == 422


def test_correction_roundtrip_keeps_identity_and_blocks_confirmation(client, order):
    reason = "Falta número de casa.\nComprueba también las cantidades."
    requested = action(client, order, "request_correction", reason).json()
    assert requested["status"] == "recibido"
    assert requested["correction_status"] == "requested"
    assert requested["correction_note"] == reason
    assert action(client, requested, "confirm").status_code == 409
    assert action(client, requested, "request_correction", "Otro motivo").status_code == 409
    assert correction(client, requested, actor="cliente-2").status_code == 404
    changed = {
        **DATA,
        "address": "Casa 25, Zona 10, Guatemala",
        "items": [{"product": "Caja corregida", "quantity": 5}],
        "location": {"latitude": 14.6, "longitude": -90.5},
    }
    result = correction(client, requested, changed)
    assert result.status_code == 200
    submitted = result.json()
    assert submitted["correction_status"] == "resubmitted"
    for field in ("id", "code", "created_at", "customer_id"):
        assert submitted[field] == order[field]
    assert submitted["address"] == changed["address"]
    assert submitted["items"] == changed["items"]
    assert submitted["location"] == changed["location"]
    assert submitted["history"][1]["note"] == reason
    assert correction(client, submitted).status_code == 409
    confirmed = action(client, submitted, "confirm").json()
    assert confirmed["status"] == "confirmado"
    assert confirmed["correction_status"] == "resolved"
    assert correction(client, confirmed).status_code == 409
    assert len(client.get(f"{ROOT}/orders", headers=CUSTOMER).json()) == 1


def test_company_can_request_another_review_after_resubmission(client, order):
    first = action(client, order, "request_correction", "Completar dirección").json()
    submitted = correction(client, first).json()
    second = action(client, submitted, "request_correction", "Falta municipio").json()
    assert second["correction_status"] == "requested"
    assert second["correction_note"] == "Falta municipio"
    assert second["history"][1]["note"] == "Completar dirección"
    assert second["history"][3]["note"] == "Falta municipio"


def test_invalid_correction_cannot_mutate_order(client, order):
    assert correction(client, order).status_code == 409
    requested = action(client, order, "request_correction", "Cambiar cantidades").json()
    for changes in ({"items": []}, {"status": "confirmado"}, {"customer_id": "cliente-2"}):
        assert correction(client, requested, {**DATA, **changes}).status_code == 422
    assert client.get(f"{ROOT}/orders/{order['code']}", headers=CUSTOMER).json() == requested


@pytest.mark.parametrize("actor", ["cliente-1", "cliente-2", "conductor", "unknown"])
def test_only_company_actor_can_operate_company_routes(client, order, actor):
    headers = {"X-Demo-Actor": actor}
    path = f"{ROOT}/company/orders/{order['code']}"
    assert client.get(f"{ROOT}/company/orders", headers=headers).status_code == 403
    assert client.get(path, headers=headers).status_code == 403
    assert (
        client.post(
            path + "/actions", headers=headers, json={"action": "confirm", "expected_revision": 1}
        ).status_code
        == 403
    )
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert (
        client.post(
            path + "/schedule",
            headers=headers,
            json={"scheduled_departure_at": future, "expected_revision": 1},
        ).status_code
        == 403
    )


@pytest.mark.parametrize("actor", ["empresa", "conductor", "unknown"])
def test_other_roles_cannot_submit_customer_corrections(client, order, actor):
    assert correction(client, order, actor=actor).status_code == 403


@pytest.mark.parametrize("reason", ["", "   ", "x" * 1001])
def test_correction_requires_meaningful_reason(client, order, reason):
    assert action(client, order, "request_correction", reason).status_code == 422
    assert client.get(f"{ROOT}/orders/{order['code']}", headers=CUSTOMER).json() == order


@pytest.mark.parametrize(
    "changes",
    [
        {"scheduled_departure_at": "2000-01-01T12:00:00Z"},
        {"scheduled_departure_at": "2035-01-01T12:00:00"},
        {"scheduled_departure_at": "invalid"},
        {"scheduled_departure_at": None},
        {"estimated_delivery_at": "2000-01-01T12:00:00Z"},
        {"estimated_delivery_at": "2035-01-01T12:00:00"},
        {"expected_revision": True},
        {"status": "entregado"},
    ],
)
def test_invalid_schedules_leave_order_unchanged(client, order, changes):
    confirmed = action(client, order, "confirm").json()
    assert schedule(client, confirmed, **changes).status_code == 422
    assert client.get(f"{ROOT}/orders/{order['code']}", headers=CUSTOMER).json() == confirmed


def test_dates_can_be_adjusted_and_eta_cleared_with_history(client, order):
    confirmed = action(client, order, "confirm").json()
    future = (datetime.now(UTC) + timedelta(days=2)).replace(tzinfo=None, microsecond=0).isoformat()
    scheduled = schedule(client, confirmed, scheduled_departure_at=future + "-06:00").json()
    assert scheduled["status"] == "confirmado"
    assert datetime.fromisoformat(scheduled["scheduled_departure_at"]) == datetime.fromisoformat(
        future + "-06:00"
    )
    assert scheduled["scheduled_departure_at"].endswith("Z")
    revised = schedule(client, scheduled, estimated_delivery_at=None).json()
    assert revised["estimated_delivery_at"] is None
    assert revised["history"][-1]["estimated_delivery_at"] is None
    assert revised["history"][-2]["estimated_delivery_at"] is not None
    assert revised["revision"] == scheduled["revision"] + 1


def test_stale_revisions_do_not_overwrite_or_repeat_changes(client, order):
    requested = action(client, order, "request_correction", "Completar dirección").json()
    assert correction(client, order).status_code == 409
    submitted = correction(client, requested).json()
    assert correction(client, requested).status_code == 409
    assert action(client, requested, "confirm").status_code == 409
    confirmed = action(client, submitted, "confirm").json()
    assert schedule(client, submitted).status_code == 409
    assert client.get(f"{ROOT}/orders/{order['code']}", headers=CUSTOMER).json() == confirmed


def test_concurrent_company_commands_only_apply_once():
    store = DemoOrderStore()
    order, _ = store.create(ACTORS[0], OrderInput(**DATA), "concurrent-company")
    actions = [
        CompanyAction(expected_revision=1, action="confirm"),
        CompanyAction(expected_revision=1, action="request_correction", note="Completar dirección"),
    ]

    def attempt(command):
        try:
            return store.act(order.code, ACTORS[2], command).revision
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, actions)) == [2, 409]
    stored = store.get_company(order.code)
    assert stored.revision == 2
    assert len(stored.history) == 2
    stored.history.clear()
    assert len(store.get_company(order.code).history) == 2


def test_company_contracts_and_local_only_mode(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert f"{ROOT}/company/orders/{{code}}/actions" in paths
    assert f"{ROOT}/company/orders/{{code}}/schedule" in paths
    assert f"{ROOT}/orders/{{code}}/correction" in paths
    assert client.get(f"{ROOT}/company/orders").status_code == 422
    with TestClient(create_app(Settings(_env_file=None, demo_mode=False))) as disabled:
        assert disabled.get(f"{ROOT}/company/orders", headers=COMPANY).status_code == 404
    with TestClient(
        create_app(Settings(_env_file=None, demo_mode=True)), client=("203.0.113.1", 50000)
    ) as remote:
        assert remote.get(f"{ROOT}/company/orders", headers=COMPANY).status_code == 403
