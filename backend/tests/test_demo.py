from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo import ACTORS, DemoOrderStore, OrderInput
from app.main import create_app


@pytest.fixture
def payload():
    return {
        "contact_name": "Cliente prueba",
        "contact_email": "cliente@example.test",
        "contact_phone": "5555 1234",
        "items": [{"product": "Caja de vasos", "quantity": 3}],
        "address": "Zona 10, Ciudad de Guatemala",
        "instructions": "Llamar al llegar",
        "location": {"latitude": 14.6, "longitude": -90.5},
    }


@pytest.fixture
def client():
    app = create_app(Settings(_env_file=None, demo_mode=True, database_url=None))
    with TestClient(app, client=("127.0.0.1", 50000)) as test_client:
        yield test_client


def headers(actor="cliente-1", key="test-request-123"):
    return {"X-Demo-Actor": actor, "Idempotency-Key": key}


def test_demo_starts_empty_without_database(client):
    assert client.get("/health/ready").json() == {"status": "demo", "storage": "memory"}
    assert client.app.state.engine is None
    context = client.get("/api/v1/demo/context").json()
    assert context["company"] == "EmpresaTest"
    assert context["storage"] == "memory"
    assert client.get("/api/v1/demo/orders", headers=headers()).json() == []


def test_create_list_and_track_after_refresh(client, payload):
    result = client.post("/api/v1/demo/orders", json=payload, headers=headers())
    assert result.status_code == 201
    order = result.json()
    assert order["code"].startswith("MON-")
    assert order["status"] == "recibido"
    assert order["customer_id"] == "cliente-1"
    assert order["estimated_delivery_at"] is None
    assert order["scheduled_departure_at"] is None
    assert order["delivery_mode"] is None
    for _ in range(2):
        assert client.get(f"/api/v1/demo/orders/{order['code']}", headers=headers()).json() == order
        assert client.get("/api/v1/demo/orders", headers=headers()).json() == [order]


def test_customers_cannot_read_each_others_orders(client, payload):
    order = client.post("/api/v1/demo/orders", json=payload, headers=headers()).json()
    assert client.get("/api/v1/demo/orders", headers=headers("cliente-2")).json() == []
    assert (
        client.get(f"/api/v1/demo/orders/{order['code']}", headers=headers("cliente-2")).status_code
        == 404
    )
    assert client.get("/api/v1/demo/orders/MON-00000000", headers=headers()).status_code == 404


def test_retries_do_not_duplicate_and_changed_payload_is_rejected(client, payload):
    first = client.post("/api/v1/demo/orders", json=payload, headers=headers())
    again = client.post("/api/v1/demo/orders", json=payload, headers=headers())
    assert again.status_code == 200
    assert first.json()["code"] == again.json()["code"]
    changed = {**payload, "address": "Otra dirección distinta"}
    assert client.post("/api/v1/demo/orders", json=changed, headers=headers()).status_code == 409
    assert len(client.get("/api/v1/demo/orders", headers=headers()).json()) == 1


@pytest.mark.parametrize("actor", ["empresa", "conductor", "unknown"])
def test_demo_role_is_not_a_customer(client, payload, actor):
    assert (
        client.post("/api/v1/demo/orders", json=payload, headers=headers(actor)).status_code == 403
    )
    assert client.get("/api/v1/demo/orders", headers=headers(actor)).status_code == 403


@pytest.mark.parametrize(
    "changes",
    [
        {"contact_name": "   "},
        {"contact_email": "invalid"},
        {"address": "x"},
        {"items": []},
        {"items": [{"product": "Caja", "quantity": 0}]},
        {"items": [{"product": "Caja", "quantity": 1.5}]},
        {"items": [{"product": "Caja", "quantity": True}]},
        {"location": {"latitude": 100, "longitude": 0}},
        {"location": {"latitude": 0, "longitude": 181}},
        {"customer_id": "cliente-2"},
        {"status": "entregado"},
    ],
)
def test_invalid_inputs_cannot_create_orders(client, payload, changes):
    assert (
        client.post(
            "/api/v1/demo/orders", json={**payload, **changes}, headers=headers()
        ).status_code
        == 422
    )
    assert client.get("/api/v1/demo/orders", headers=headers()).json() == []


def test_map_is_optional_and_missing_actor_and_key_are_rejected(client, payload):
    no_map = {**payload, "location": None}
    assert client.post("/api/v1/demo/orders", json=no_map, headers=headers()).status_code == 201
    assert client.post("/api/v1/demo/orders", json=payload).status_code == 422
    assert (
        client.post(
            "/api/v1/demo/orders", json=payload, headers={"X-Demo-Actor": "cliente-1"}
        ).status_code
        == 422
    )


def test_demo_routes_are_absent_when_disabled():
    with TestClient(
        create_app(Settings(_env_file=None, demo_mode=False, database_url=None))
    ) as client:
        assert client.get("/api/v1/demo/context").status_code == 404
        assert client.get("/api/v1/demo/orders").status_code == 404
        assert client.get("/health/ready").status_code == 503


def test_demo_rejects_remote_clients():
    with TestClient(
        create_app(Settings(_env_file=None, demo_mode=True)), client=("203.0.113.1", 50000)
    ) as client:
        assert client.get("/api/v1/demo/context").status_code == 403
        assert client.get("/health/ready").status_code == 403


def test_backend_restart_clears_orders(payload):
    app = create_app(Settings(_env_file=None, demo_mode=True))
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        client.post("/api/v1/demo/orders", json=payload, headers=headers())
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert client.get("/api/v1/demo/orders", headers=headers()).json() == []


def test_concurrent_submissions_share_a_single_order_and_results_are_copies(payload):
    store = DemoOrderStore()
    request = OrderInput(**deepcopy(payload))
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(
            executor.map(lambda _: store.create(ACTORS[0], request, "same-key"), range(12))
        )
    assert len({order.code for order, _ in results}) == 1
    assert sum(created for _, created in results) == 1
    results[0][0].items[0].quantity = 900
    assert store.list_for(ACTORS[0].id)[0].items[0].quantity == 3
