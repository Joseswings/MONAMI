from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from test_fleet import assign, snapshot
from test_fleet import client as client
from test_fleet import make_order as make_order
from test_incidents import on_road as on_road
from test_incidents import problem, read_trip, report, reprogram, resolve
from test_partners import request_service, service_action
from test_trips import act, create_trip
from test_trips import trip as trip

from app.config import Settings
from app.main import create_app

ROOT = "/api/v1/demo"
COMPANY = {"X-Demo-Actor": "empresa"}
DRIVER = {"X-Demo-Actor": "conductor"}
CUSTOMER = {"X-Demo-Actor": "cliente-1"}


def own_order(client, code):
    return client.get(f"{ROOT}/orders/{code}", headers=CUSTOMER).json()


def deliver(client, trip, index=0, actor="conductor", **changes):
    stop = trip["stops"][index]
    return client.post(
        f"{ROOT}/driver/trips/{trip['id']}/orders/{stop['code']}/deliver",
        headers={"X-Demo-Actor": actor},
        json={
            "expected_revision": trip["revision"],
            "expected_order_revision": stop["order_revision"],
            "note": "Recibido en la dirección de prueba",
            **changes,
        },
    )


@pytest.mark.parametrize("advances", [0, 1, 4])
def test_delivery_is_explicit_and_does_not_require_full_route(client, on_road, advances):
    current = on_road
    for _ in range(advances):
        current = act(client, current, "advance").json()
    first, second = current["order_codes"]
    original = own_order(client, first)
    other = own_order(client, second)
    response = deliver(client, current)
    assert response.status_code == 200
    partial = response.json()
    delivered = own_order(client, first)
    assert delivered["id"] == original["id"] and delivered["code"] == first
    assert delivered["status"] == "entregado" and delivered["delivered_at"]
    assert delivered["delivered_by"] == "Conductor de prueba"
    assert delivered["delivery_note"] == "Recibido en la dirección de prueba"
    assert datetime.fromisoformat(delivered["delivered_at"]) >= datetime.fromisoformat(
        original["actual_departure_at"]
    )
    assert partial["progress_percent"] == current["progress_percent"]
    assert partial["position"] == current["position"]
    assert partial["completed_order_codes"] == [first]
    assert partial["status"] == "en_camino" and partial["closed_at"] is None
    assert partial["stops"][0]["delivery_status"] == "entregado"
    assert partial["stops"][0]["delivered_at"] == delivered["delivered_at"]
    assert own_order(client, second) == other
    truck = snapshot(client)["trucks"][0]
    assert truck["order_codes"] == [second] and truck["used_capacity"] == 3
    assert truck["trip_id"] == current["id"]
    assert (
        client.get(f"{ROOT}/company/trips", headers=COMPANY).json()["drivers"][0]["available"]
        is False
    )


def test_final_delivery_closes_trip_preserves_manifest_and_releases_resources(
    client, on_road, make_order
):
    first = deliver(client, on_road).json()
    finished = deliver(client, first, index=1).json()
    assert finished["status"] == "completado" and finished["closed_at"]
    assert finished["order_codes"] == on_road["order_codes"]
    assert len(finished["stops"]) == 2 and len(finished["completed_order_codes"]) == 2
    assert client.get(f"{ROOT}/driver/trip", headers=DRIVER).json() is None
    archive = client.get(f"{ROOT}/driver/trips", headers=DRIVER).json()
    assert archive == [finished]
    assert client.get(f"{ROOT}/driver/trips", headers={"X-Demo-Actor": "conductor-2"}).json() == []
    assert (
        client.get(
            f"{ROOT}/driver/trips/{finished['id']}", headers={"X-Demo-Actor": "conductor-2"}
        ).status_code
        == 404
    )
    truck = snapshot(client)["trucks"][0]
    assert truck["availability"] == "disponible" and truck["order_codes"] == []
    assert truck["trip_id"] is None and truck["used_capacity"] == 0
    assert client.get(f"{ROOT}/company/trips", headers=COMPANY).json()["drivers"][0]["available"]
    another = make_order()
    assert assign(client, [another["code"]]).status_code == 200
    assert create_trip(client).status_code == 201
    assert read_trip(client, finished["id"]) == finished


def test_delivered_tracking_is_frozen_while_other_orders_continue(client, on_road):
    partial = deliver(client, on_road).json()
    code = partial["order_codes"][0]
    frozen = own_order(client, code)
    tracking = client.get(f"{ROOT}/orders/{code}/tracking", headers=CUSTOMER).json()
    assert tracking["status"] == "entregado" and tracking["delivered_at"] == frozen["delivered_at"]
    assert tracking["position"] is None and tracking["incident_message"] is None
    assert partial["order_codes"][1] not in str(tracking)
    assert not {"stops", "order_codes", "history"} & tracking.keys()
    assert (
        client.get(
            f"{ROOT}/orders/{code}/tracking", headers={"X-Demo-Actor": "cliente-2"}
        ).status_code
        == 404
    )
    advanced = act(client, partial, "advance").json()
    blocked = report(client, advanced).json()
    resumed = resolve(client, blocked).json()
    assert own_order(client, code) == frozen
    assert client.get(f"{ROOT}/orders/{code}/tracking", headers=CUSTOMER).json() == tracking
    assert resumed["stops"][0]["delivery_status"] == "entregado"


@pytest.mark.parametrize("delivery_first", [False, True])
def test_mixed_delivery_and_reschedule_closes_original_trip(client, on_road, delivery_first):
    current = on_road
    if delivery_first:
        current = deliver(client, current).json()
    failed = problem(client, current, index=1).json()
    if delivery_first:
        failed = report(client, failed).json()
    ready = reprogram(client, failed, index=1).json()
    current = read_trip(client, on_road["id"])
    if not delivery_first:
        current = deliver(client, current).json()
    assert current["status"] == "completado" and current["closed_at"]
    assert len(current["completed_order_codes"]) == len(current["excluded_order_codes"]) == 1
    assert current["active_incident_id"] is None
    assert own_order(client, ready["code"]) == ready
    assert snapshot(client)["trucks"][0]["availability"] == "disponible"


def test_problem_must_be_reprogrammed_before_a_later_delivery(client, on_road):
    failed = problem(client, on_road).json()
    assert deliver(client, failed).status_code == 409
    ready = reprogram(client, failed).json()
    assert (
        assign(
            client,
            [ready["code"]],
            truck="camion-2",
            day=datetime.fromisoformat(ready["scheduled_departure_at"]).date(),
        ).status_code
        == 200
    )
    assigned = create_trip(client, truck="camion-2", driver="conductor-2").json()
    loaded = act(client, assigned, "confirm_load", actor="conductor-2").json()
    started = act(client, loaded, "start_trip", actor="conductor-2").json()
    result = deliver(client, started, actor="conductor-2")
    assert result.status_code == 200
    delivered = own_order(client, ready["code"])
    assert delivered["status"] == "entregado" and delivered["id"] == ready["id"]
    assert delivered["delivery_attempts"] == ready["delivery_attempts"]


def test_incident_must_be_resolved_before_delivery(client, on_road):
    blocked = report(client, on_road).json()
    before = own_order(client, blocked["order_codes"][0])
    assert deliver(client, blocked).status_code == 409
    assert own_order(client, before["code"]) == before
    resumed = resolve(client, blocked).json()
    assert deliver(client, resumed).status_code == 200


def test_delivery_needs_started_trip_and_current_revisions(client, trip):
    assert deliver(client, trip).status_code == 409
    loaded = act(client, trip, "confirm_load").json()
    assert deliver(client, loaded).status_code == 409
    started = act(client, loaded, "start_trip").json()
    assert deliver(client, started, expected_order_revision=1).status_code == 409
    advanced = act(client, started, "advance").json()
    assert deliver(client, started).status_code == 409
    partial = deliver(client, advanced).json()
    assert deliver(client, advanced).status_code == 409
    assert deliver(client, partial).status_code == 404
    assert problem(client, partial).status_code == 404


@pytest.mark.parametrize(
    "actor,expected",
    [
        ("empresa", 403),
        ("cliente-1", 403),
        ("cliente-2", 403),
        ("conductor-2", 404),
        ("desconocido", 403),
    ],
)
def test_only_assigned_driver_can_confirm_own_delivery(client, on_road, actor, expected):
    assert deliver(client, on_road, actor=actor).status_code == expected
    assert read_trip(client, on_road["id"]) == on_road


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_revision": True},
        {"expected_order_revision": True},
        {"expected_order_revision": 0},
        {"note": "x" * 1001},
        {"delivered_at": "2030-01-01T00:00:00Z"},
        {"status": "entregado"},
        {"delivered_by": "empresa"},
    ],
)
def test_delivery_rejects_invalid_and_forged_fields(client, on_road, changes):
    assert deliver(client, on_road, **changes).status_code == 422
    assert read_trip(client, on_road["id"]) == on_road


def test_closed_and_delivered_orders_are_terminal(client, on_road):
    partial = deliver(client, on_road).json()
    finished = deliver(client, partial, index=1).json()
    order = own_order(client, finished["order_codes"][0])
    assert deliver(client, finished).status_code == 409
    assert act(client, finished, "advance").status_code == 409
    assert report(client, finished).status_code == 409
    assert request_service(client, order).status_code == 409
    assert assign(client, [order["code"]]).status_code == 409
    scheduled = client.post(
        f"{ROOT}/company/orders/{order['code']}/schedule",
        headers=COMPANY,
        json={
            "expected_revision": order["revision"],
            "scheduled_departure_at": (datetime.now(UTC) + timedelta(days=10)).isoformat(),
        },
    )
    assert scheduled.status_code == 409
    assert own_order(client, order["code"]) == order


@pytest.mark.parametrize("competitor", ["advance", "problem", "deliver"])
def test_delivery_races_are_atomic(client, on_road, competitor):
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(deliver, client, on_road)
        if competitor == "advance":
            second = executor.submit(act, client, on_road, "advance")
        elif competitor == "problem":
            second = executor.submit(problem, client, on_road)
        else:
            second = executor.submit(deliver, client, on_road, index=1)
        assert sorted([first.result().status_code, second.result().status_code]) == [200, 409]
    current = read_trip(client, on_road["id"])
    assert current["revision"] == on_road["revision"] + 1


@pytest.mark.parametrize("advance_first", [False, True])
def test_company_confirms_third_party_delivery_after_dispatch(client, make_order, advance_first):
    original = make_order()
    pending = request_service(client, original).json()
    assert service_action(client, pending, "deliver").status_code == 409
    confirmed = service_action(client, pending, "confirm").json()
    assert service_action(client, confirmed, "deliver").status_code == 409
    dispatched = service_action(client, confirmed, "dispatch").json()
    if advance_first:
        for _ in range(4):
            dispatched = service_action(client, dispatched, "advance").json()
    delivered = service_action(
        client, dispatched, "deliver", note="Entrega de prueba confirmada"
    ).json()
    assert delivered["status"] == "entregado" and delivered["third_party"]["status"] == "entregado"
    assert delivered["delivered_by"] == "EmpresaTest"
    assert delivered["delivered_at"] == delivered["third_party"]["delivered_at"]
    assert delivered["id"] == original["id"] and delivered["code"] == original["code"]
    assert delivered["delivery_note"] == "Entrega de prueba confirmada"
    assert own_order(client, original["code"]) == delivered
    tracking = client.get(f"{ROOT}/orders/{original['code']}/tracking", headers=CUSTOMER).json()
    assert tracking["status"] == "entregado" and tracking["position"] is None
    assert tracking["delivered_at"] == delivered["delivered_at"]
    for action in ("deliver", "advance", "cancel", "confirm", "dispatch"):
        assert service_action(client, delivered, action, note="Prueba").status_code == 409
    assert own_order(client, original["code"]) == delivered


@pytest.mark.parametrize("actor", ["cliente-1", "cliente-2", "conductor", "conductor-2"])
def test_third_party_delivery_is_company_only(client, make_order, actor):
    pending = request_service(client, make_order()).json()
    confirmed = service_action(client, pending, "confirm").json()
    dispatched = service_action(client, confirmed, "dispatch").json()
    assert service_action(client, dispatched, "deliver", actor=actor).status_code == 403


def test_double_confirmation_does_not_duplicate_third_party_history(client, make_order):
    pending = request_service(client, make_order()).json()
    confirmed = service_action(client, pending, "confirm").json()
    dispatched = service_action(client, confirmed, "dispatch").json()
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(lambda _: service_action(client, dispatched, "deliver"), range(2))
        )
    assert sorted(result.status_code for result in responses) == [200, 409]
    result = own_order(client, dispatched["code"])
    assert result["revision"] == dispatched["revision"] + 1
    assert len(result["third_party"]["history"]) == len(dispatched["third_party"]["history"]) + 1


def test_delivery_and_closed_trip_routes_are_local_and_disabled_without_demo():
    with TestClient(
        create_app(Settings(_env_file=None, demo_mode=True)), client=("192.0.2.1", 50000)
    ) as remote:
        assert remote.get(f"{ROOT}/driver/trips", headers=DRIVER).status_code == 403
        assert (
            remote.post(
                f"{ROOT}/driver/trips/id/orders/MON-12345678/deliver",
                headers=DRIVER,
                json={"expected_revision": 1, "expected_order_revision": 1},
            ).status_code
            == 403
        )
    with TestClient(create_app(Settings(_env_file=None, demo_mode=False))) as real:
        paths = real.get("/openapi.json").json()["paths"]
        assert f"{ROOT}/driver/trips" not in paths
        assert f"{ROOT}/driver/trips/{{trip_id}}/orders/{{code}}/deliver" not in paths
