from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo import ACTORS
from app.demo_fleet import AssignmentInput
from app.main import create_app

ROOT = "/api/v1/demo"
FLEET = f"{ROOT}/company"
COMPANY = {"X-Demo-Actor": "empresa"}
CUSTOMER = {"X-Demo-Actor": "cliente-1"}
DAY = (datetime.now(UTC) + timedelta(days=3)).date()
GUATEMALA = timezone(timedelta(hours=-6))


@pytest.fixture
def client():
    with TestClient(
        create_app(Settings(_env_file=None, demo_mode=True)), client=("127.0.0.1", 50000)
    ) as client:
        yield client


def snapshot(client):
    response = client.get(f"{FLEET}/planning", headers=COMPANY)
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def make_order(client):
    sequence = 0

    def create(quantity=3, location=None, day=DAY, ready=True, items=None):
        nonlocal sequence
        sequence += 1
        data = {
            "contact_name": "Cliente de prueba",
            "contact_email": "cliente@empresatest.test",
            "contact_phone": "55551234",
            "address": f"Casa {sequence}, Zona 10, Guatemala",
            "items": items or [{"product": "Caja", "quantity": quantity}],
            "location": location,
        }
        response = client.post(
            f"{ROOT}/orders",
            headers={**CUSTOMER, "Idempotency-Key": f"fleet-order-{sequence}"},
            json=data,
        )
        assert response.status_code == 201
        order = response.json()
        if not ready:
            return order
        path = f"{FLEET}/orders/{order['code']}"
        for action in ("confirm", "start_preparation"):
            response = client.post(
                path + "/actions",
                headers=COMPANY,
                json={"action": action, "expected_revision": order["revision"]},
            )
            assert response.status_code == 200
            order = response.json()
        response = client.post(
            path + "/schedule",
            headers=COMPANY,
            json={
                "scheduled_departure_at": datetime.combine(
                    day, time(9), tzinfo=GUATEMALA
                ).isoformat(),
                "expected_revision": order["revision"],
            },
        )
        assert response.status_code == 200
        order = response.json()
        response = client.post(
            path + "/actions",
            headers=COMPANY,
            json={"action": "mark_ready", "expected_revision": order["revision"]},
        )
        assert response.status_code == 200
        return response.json()

    return create


def assign(client, codes, truck="camion-1", day=DAY, revision=None):
    return client.post(
        f"{FLEET}/trucks/{truck}/assignment",
        headers=COMPANY,
        json={
            "expected_revision": snapshot(client)["revision"] if revision is None else revision,
            "departure_date": day.isoformat() if codes else None,
            "order_codes": codes,
        },
    )


def suggest(client, truck="camion-1", day=DAY, revision=None):
    return client.post(
        f"{FLEET}/trucks/{truck}/suggestion",
        headers=COMPANY,
        json={
            "expected_revision": snapshot(client)["revision"] if revision is None else revision,
            "departure_date": day.isoformat(),
        },
    )


def test_fleet_starts_with_empty_available_trucks(client):
    data = snapshot(client)
    assert data["ready_orders"] == []
    assert [truck["capacity"] for truck in data["trucks"]] == [20, 40, 60]
    for truck in data["trucks"]:
        assert truck["availability"] == "disponible"
        assert truck["order_codes"] == []
        assert truck["departure_date"] is None
        assert truck["used_capacity"] == 0
        assert truck["remaining_capacity"] == truck["capacity"]


def test_only_ready_orders_are_assignable(client, make_order):
    received = make_order(ready=False)
    ready = make_order()
    assert [o["code"] for o in snapshot(client)["ready_orders"]] == [ready["code"]]
    before = snapshot(client)
    assert assign(client, [received["code"]]).status_code == 409
    assert snapshot(client) == before


def test_capacity_reservation_and_customer_transport(client, make_order):
    first = make_order(
        items=[{"product": "Caja", "quantity": 3}, {"product": "Paquete", "quantity": 2}]
    )
    second = make_order(quantity=15)
    response = assign(client, [first["code"], second["code"]])
    assert response.status_code == 200
    data = response.json()
    truck = data["trucks"][0]
    assert truck["used_capacity"] == 20
    assert truck["remaining_capacity"] == 0
    assert truck["availability"] == "completo"
    assert truck["departure_date"] == DAY.isoformat()
    tracked = client.get(f"{ROOT}/orders/{first['code']}", headers=CUSTOMER).json()
    assert tracked["delivery_mode"] == "flota_propia"
    assert tracked["assigned_truck_id"] == "camion-1"
    assert tracked["assigned_truck_name"] == truck["name"]
    assert tracked["status"] == "listo_para_salir"
    assert tracked["revision"] == first["revision"] + 1
    assert second["code"] not in str(tracked)


def test_over_capacity_is_rejected_atomically(client, make_order):
    first, second = make_order(quantity=15), make_order(quantity=8)
    before = snapshot(client)
    assert assign(client, [first["code"], second["code"]]).status_code == 409
    assert snapshot(client) == before
    assert client.get(f"{ROOT}/orders/{first['code']}", headers=CUSTOMER).json() == first
    assert assign(client, [first["code"]]).status_code == 200
    reserved = snapshot(client)
    assert assign(client, [first["code"], second["code"]]).status_code == 409
    assert snapshot(client) == reserved


def test_release_and_transfer_update_both_capacities(client, make_order):
    order = make_order(quantity=8)
    assigned = assign(client, [order["code"]]).json()
    assert assigned["trucks"][0]["availability"] == "reservado"
    before = snapshot(client)
    assert assign(client, [order["code"]], truck="camion-2").status_code == 409
    assert snapshot(client) == before
    released = assign(client, []).json()
    assert released["trucks"][0]["availability"] == "disponible"
    tracked = client.get(f"{ROOT}/orders/{order['code']}", headers=CUSTOMER).json()
    assert tracked["assigned_truck_id"] is None
    assert tracked["delivery_mode"] is None
    assert tracked["history"][-1]["action"] == "Pedido retirado del camión"
    moved = assign(client, [order["code"]], truck="camion-2").json()
    assert moved["trucks"][0]["used_capacity"] == 0
    assert moved["trucks"][1]["used_capacity"] == 8


def test_reorder_preserves_load_and_retries_do_not_duplicate_history(client, make_order):
    first, second = make_order(), make_order()
    original = assign(client, [first["code"], second["code"]]).json()
    result = assign(client, [second["code"], first["code"]]).json()
    truck = result["trucks"][0]
    assert truck["order_codes"] == [second["code"], first["code"]]
    assert [stop["position"] for stop in truck["stops"]] == [1, 2]
    assert truck["used_capacity"] == original["trucks"][0]["used_capacity"]
    assert assign(client, truck["order_codes"]).json() == result
    tracked = client.get(f"{ROOT}/orders/{first['code']}", headers=CUSTOMER).json()
    assert tracked["history"][-1]["action"] == "Orden de parada ajustado"
    assert assign(client, truck["order_codes"], revision=original["revision"]).status_code == 409


def test_suggestion_uses_proximity_capacity_day_and_coordinates_without_mutation(
    client, make_order
):
    near = make_order(quantity=6, location={"latitude": 14.635, "longitude": -90.507})
    far = make_order(quantity=6, location={"latitude": 14.9, "longitude": -90.8})
    oversized = make_order(quantity=30, location={"latitude": 14.636, "longitude": -90.508})
    no_point = make_order()
    other_day = make_order(
        day=DAY + timedelta(days=1), location={"latitude": 14.635, "longitude": -90.507}
    )
    before = snapshot(client)
    response = suggest(client)
    assert response.status_code == 200
    proposal = response.json()
    assert proposal["order_codes"] == [near["code"], far["code"]]
    assert {item["code"] for item in proposal["excluded"]} == {oversized["code"], no_point["code"]}
    assert other_day["code"] not in str(proposal)
    assert snapshot(client) == before


def test_suggestion_keeps_existing_order_and_ignores_other_trucks(client, make_order):
    far = make_order(location={"latitude": 14.9, "longitude": -90.8})
    near = make_order(location={"latitude": 14.635, "longitude": -90.507})
    other = make_order(location={"latitude": 14.636, "longitude": -90.508})
    assign(client, [far["code"]])
    assign(client, [other["code"]], truck="camion-2")
    proposal = suggest(client).json()
    assert proposal["order_codes"] == [far["code"], near["code"]]
    assert other["code"] not in str(proposal)


def test_missing_coordinates_allow_manual_assignment_but_route_stays_incomplete(client, make_order):
    order = make_order()
    data = assign(client, [order["code"]]).json()
    truck = data["trucks"][0]
    assert truck["route_complete"] is False
    assert truck["straight_line_km"] is None
    assert truck["stops"][0]["location"] is None
    assert data["ready_orders"][0]["status"] == "listo_para_salir"


def test_route_reports_numbered_points_and_only_geometric_distance(client, make_order):
    first = make_order(location={"latitude": 14.6349, "longitude": -90.5069})
    second = make_order(location={"latitude": 14.7349, "longitude": -90.5069})
    data = assign(client, [first["code"], second["code"]]).json()
    truck = data["trucks"][0]
    assert truck["route_complete"] is True
    assert 11 < truck["straight_line_km"] < 12
    assert [stop["code"] for stop in truck["stops"]] == [first["code"], second["code"]]
    data["trucks"][0]["order_codes"].clear()
    assert len(snapshot(client)["trucks"][0]["order_codes"]) == 2
    projection = client.app.state.demo_orders.planning()
    projection.trucks[0].stops[0].location.latitude = 0
    projection.trucks[0].order_codes.clear()
    current = client.app.state.demo_orders.planning()
    assert current.trucks[0].stops[0].location.latitude == 14.6349
    assert len(current.trucks[0].order_codes) == 2


def test_mixed_days_and_second_reservation_are_rejected(client, make_order):
    first, second = make_order(), make_order(day=DAY + timedelta(days=1))
    before = snapshot(client)
    assert assign(client, [first["code"], second["code"]]).status_code == 409
    assert snapshot(client) == before
    assign(client, [first["code"]])
    assert suggest(client, day=DAY + timedelta(days=1)).status_code == 409
    assert assign(client, [second["code"]], day=DAY + timedelta(days=1)).status_code == 409
    assign(client, [])
    assert assign(client, [second["code"]], day=DAY + timedelta(days=1)).status_code == 200


def test_assigned_order_day_is_locked_but_same_local_day_time_is_editable(client, make_order):
    order = make_order()
    assign(client, [order["code"]])
    order = client.get(f"{ROOT}/orders/{order['code']}", headers=CUSTOMER).json()
    path = f"{FLEET}/orders/{order['code']}/schedule"
    before = snapshot(client)
    changed_day = datetime.combine(DAY + timedelta(days=1), time(9), tzinfo=GUATEMALA)
    assert (
        client.post(
            path,
            headers=COMPANY,
            json={
                "expected_revision": order["revision"],
                "scheduled_departure_at": changed_day.isoformat(),
            },
        ).status_code
        == 409
    )
    assert snapshot(client) == before
    early_same_day = datetime.combine(DAY, time(1), tzinfo=GUATEMALA)
    response = client.post(
        path,
        headers=COMPANY,
        json={
            "expected_revision": order["revision"],
            "scheduled_departure_at": early_same_day.isoformat(),
        },
    )
    assert response.status_code == 200
    assert snapshot(client)["revision"] > before["revision"]
    assert snapshot(client)["trucks"][0]["departure_date"] == DAY.isoformat()


def test_grouping_uses_guatemala_day_instead_of_utc_day(client, make_order):
    order = make_order()
    # UTC 02:00 del día siguiente todavía pertenece al día de salida local.
    utc_departure = datetime.combine(DAY + timedelta(days=1), time(2), tzinfo=UTC)
    response = client.post(
        f"{FLEET}/orders/{order['code']}/schedule",
        headers=COMPANY,
        json={
            "expected_revision": order["revision"],
            "scheduled_departure_at": utc_departure.isoformat(),
        },
    )
    assert response.status_code == 200
    assert assign(client, [order["code"]]).status_code == 200


def test_ready_orders_and_schedule_changes_invalidate_old_drafts(client, make_order):
    first = make_order()
    revision = snapshot(client)["revision"]
    make_order()
    assert assign(client, [first["code"]], revision=revision).status_code == 409
    assert suggest(client, revision=revision).status_code == 409
    before = snapshot(client)
    new_time = datetime.combine(DAY, time(11), tzinfo=GUATEMALA)
    response = client.post(
        f"{FLEET}/orders/{first['code']}/schedule",
        headers=COMPANY,
        json={
            "expected_revision": first["revision"],
            "scheduled_departure_at": new_time.isoformat(),
        },
    )
    assert response.status_code == 200
    assert assign(client, [first["code"]], revision=before["revision"]).status_code == 409


@pytest.mark.parametrize("actor", ["cliente-1", "cliente-2", "conductor", "unknown"])
def test_only_company_can_view_suggest_or_assign(client, actor):
    headers = {"X-Demo-Actor": actor}
    assert client.get(f"{FLEET}/planning", headers=headers).status_code == 403
    assert (
        client.post(
            f"{FLEET}/trucks/camion-1/suggestion",
            headers=headers,
            json={"expected_revision": 1, "departure_date": DAY.isoformat()},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{FLEET}/trucks/camion-1/assignment",
            headers=headers,
            json={"expected_revision": 1, "order_codes": []},
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"order_codes": ["invalid"], "departure_date": DAY.isoformat()},
        {"order_codes": ["MON-ABCDEF12", "mon-abcdef12"], "departure_date": DAY.isoformat()},
        {"order_codes": ["MON-ABCDEF12"], "departure_date": None},
        {"order_codes": [], "departure_date": DAY.isoformat()},
        {"expected_revision": True},
        {"capacity": 1000},
        {"departure_date": "invalid"},
    ],
)
def test_invalid_assignment_contracts_do_not_change_state(client, changes):
    before = snapshot(client)
    response = client.post(
        f"{FLEET}/trucks/camion-1/assignment",
        headers=COMPANY,
        json={"expected_revision": before["revision"], "order_codes": [], **changes},
    )
    assert response.status_code == 422
    assert snapshot(client) == before


def test_unknown_truck_or_order_and_case_normalization(client, make_order):
    assert assign(client, [], truck="unknown").status_code == 404
    assert suggest(client, truck="unknown").status_code == 404
    before = snapshot(client)
    assert assign(client, ["MON-00000000"]).status_code == 404
    assert snapshot(client) == before
    order = make_order()
    assert assign(client, [order["code"].lower()]).status_code == 200


def test_competing_truck_assignments_cannot_reserve_the_same_order(client, make_order):
    order = make_order()
    store = client.app.state.demo_orders
    command = AssignmentInput(
        expected_revision=store.planning().revision, departure_date=DAY, order_codes=[order["code"]]
    )

    def attempt(truck):
        try:
            store.assign(truck, ACTORS[2], command)
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, ["camion-1", "camion-2"])) == [200, 409]
    trucks = store.planning().trucks
    assert sum(truck.used_capacity for truck in trucks) == 3
    assert sum(len(truck.order_codes) for truck in trucks) == 1


def test_planning_contracts_local_only_disabled_and_restart(client, make_order):
    paths = client.get("/openapi.json").json()["paths"]
    assert f"{FLEET}/planning" in paths
    assert f"{FLEET}/trucks/{{truck_id}}/assignment" in paths
    order = make_order()
    assign(client, [order["code"]])
    with TestClient(
        create_app(Settings(_env_file=None, demo_mode=True)), client=("127.0.0.1", 50000)
    ) as fresh:
        assert snapshot(fresh)["trucks"][0]["used_capacity"] == 0
        assert snapshot(fresh)["ready_orders"] == []
    with TestClient(create_app(Settings(_env_file=None, demo_mode=False))) as disabled:
        assert disabled.get(f"{FLEET}/planning", headers=COMPANY).status_code == 404
    with TestClient(
        create_app(Settings(_env_file=None, demo_mode=True)), client=("203.0.113.1", 50000)
    ) as remote:
        assert remote.get(f"{FLEET}/planning", headers=COMPANY).status_code == 403
