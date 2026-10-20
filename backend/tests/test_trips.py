from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_fleet import DAY, assign, snapshot
from test_fleet import client as client
from test_fleet import make_order as make_order

from app.config import Settings
from app.demo import ACTORS, RevisionInput
from app.demo_trips import DriverAction, TripInput
from app.main import create_app

ROOT = "/api/v1/demo"
COMPANY = {"X-Demo-Actor": "empresa"}
DRIVER = {"X-Demo-Actor": "conductor"}
OTHER_DRIVER = {"X-Demo-Actor": "conductor-2"}
CUSTOMER = {"X-Demo-Actor": "cliente-1"}


def dispatch(client):
    response = client.get(f"{ROOT}/company/trips", headers=COMPANY)
    assert response.status_code == 200
    return response.json()


def create_trip(client, truck="camion-1", driver="conductor", revision=None):
    return client.post(
        f"{ROOT}/company/trips",
        headers=COMPANY,
        json={
            "truck_id": truck,
            "driver_id": driver,
            "expected_revision": dispatch(client)["revision"] if revision is None else revision,
        },
    )


def act(client, trip, action, actor="conductor"):
    return client.post(
        f"{ROOT}/driver/trips/{trip['id']}/actions",
        headers={"X-Demo-Actor": actor},
        json={
            "action": action,
            "expected_revision": trip["revision"],
        },
    )


def cancel(client, trip):
    return client.post(
        f"{ROOT}/company/trips/{trip['id']}/cancel",
        headers=COMPANY,
        json={"expected_revision": trip["revision"]},
    )


@pytest.fixture
def trip(client, make_order):
    first = make_order(
        quantity=4,
        location={"latitude": 14.64, "longitude": -90.51},
        items=[{"product": "Vasos", "quantity": 4}, {"product": "Platos", "quantity": 2}],
    )
    second = make_order(quantity=3, location={"latitude": 14.7, "longitude": -90.6})
    assert assign(client, [first["code"], second["code"]]).status_code == 200
    response = create_trip(client)
    assert response.status_code == 201
    return response.json()


def test_driver_and_dispatch_start_empty(client):
    assert client.get(f"{ROOT}/driver/trip", headers=DRIVER).json() is None
    data = dispatch(client)
    assert data["trips"] == []
    assert data["dispatchable_trucks"] == []
    assert {driver["id"] for driver in data["drivers"]} == {"conductor", "conductor-2"}
    assert all(driver["available"] for driver in data["drivers"])
    assert create_trip(client).status_code == 409


def test_manifest_preserves_products_contacts_order_and_capacity(client, trip):
    assert trip["status"] == "asignado"
    assert trip["load_units"] == 9
    assert trip["capacity"] == 20
    assert [stop["position"] for stop in trip["stops"]] == [1, 2]
    assert trip["order_codes"] == [stop["code"] for stop in trip["stops"]]
    assert trip["stops"][0]["items"] == [
        {"product": "Vasos", "quantity": 4},
        {"product": "Platos", "quantity": 2},
    ]
    assert trip["stops"][0]["contact_phone"] == "55551234"
    assert trip["stops"][0]["contact_email"] == "cliente@empresatest.test"
    assert client.get(f"{ROOT}/driver/trip", headers=DRIVER).json() == trip
    assert client.get(f"{ROOT}/driver/trips/{trip['id']}", headers=DRIVER).json() == trip
    assert client.get(f"{ROOT}/driver/trip", headers=OTHER_DRIVER).json() is None
    assert client.get(f"{ROOT}/driver/trips/{trip['id']}", headers=OTHER_DRIVER).status_code == 404
    assert act(client, trip, "confirm_load", actor="conductor-2").status_code == 404


def test_load_departure_and_simulation_are_shared_without_confirming_delivery(client, trip):
    assert act(client, trip, "start_trip").status_code == 409
    assert act(client, trip, "advance").status_code == 409
    loaded = act(client, trip, "confirm_load").json()
    assert loaded["status"] == "carga_confirmada"
    assert act(client, loaded, "confirm_load").status_code == 409
    response = act(client, loaded, "start_trip")
    assert response.status_code == 200
    current = response.json()
    assert current["status"] == "en_camino"
    assert current["position"] == current["depot"]
    assert current["actual_departure_at"] is not None
    assert snapshot(client)["trucks"][0]["availability"] == "en_viaje"
    assert snapshot(client)["ready_orders"] == []
    assert act(client, loaded, "start_trip").status_code == 409
    for expected in (25, 50, 75, 100):
        response = act(client, current, "advance")
        assert response.status_code == 200
        current = response.json()
        assert current["progress_percent"] == expected
        assert current["position"] is not None
        assert dispatch(client)["trips"][0] == current
        for code in current["order_codes"]:
            tracked = client.get(f"{ROOT}/orders/{code}", headers=CUSTOMER).json()
            projection = client.get(f"{ROOT}/orders/{code}/tracking", headers=CUSTOMER).json()
            assert tracked["status"] == "en_camino"
            assert tracked["delivered_at"] is None
            assert tracked["actual_departure_at"] == current["actual_departure_at"]
            assert projection["progress_percent"] == expected
            assert projection["position"] == current["position"]
    assert current["position"] == current["stops"][-1]["location"]
    assert act(client, current, "advance").status_code == 409
    assert cancel(client, current).status_code == 409
    assert len(current["history"]) == 7


def test_trip_locks_manifest_and_dates_until_released(client, trip):
    before = snapshot(client)
    assert before["trucks"][0]["availability"] == "viaje_asignado"
    assert before["trucks"][0]["trip_id"] == trip["id"]
    assert assign(client, []).status_code == 409
    assert (
        client.post(
            f"{ROOT}/company/trucks/camion-1/suggestion",
            headers=COMPANY,
            json={"expected_revision": before["revision"], "departure_date": DAY.isoformat()},
        ).status_code
        == 409
    )
    order = client.get(f"{ROOT}/orders/{trip['order_codes'][0]}", headers=CUSTOMER).json()
    assert (
        client.post(
            f"{ROOT}/company/orders/{order['code']}/schedule",
            headers=COMPANY,
            json={
                "expected_revision": order["revision"],
                "scheduled_departure_at": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
            },
        ).status_code
        == 409
    )
    assert snapshot(client) == before
    released = cancel(client, trip)
    assert released.status_code == 200
    assert released.json()["status"] == "cancelado"
    assert client.get(f"{ROOT}/driver/trip", headers=DRIVER).json() is None
    assert snapshot(client)["trucks"][0]["trip_id"] is None
    assert snapshot(client)["trucks"][0]["used_capacity"] == 9
    assert cancel(client, released.json()).status_code == 409
    assert assign(client, []).status_code == 200
    tracked = client.get(f"{ROOT}/orders/{order['code']}", headers=CUSTOMER).json()
    assert tracked["trip_id"] is None
    assert tracked["assigned_driver_name"] is None
    assert tracked["status"] == "listo_para_salir"


def test_loaded_trip_can_be_released_and_an_old_trip_cannot_unlock_new_trip(client, trip):
    loaded = act(client, trip, "confirm_load").json()
    old = cancel(client, loaded).json()
    replacement = create_trip(client).json()
    assert replacement["id"] != old["id"]
    assert cancel(client, old).status_code == 409
    assert act(client, old, "start_trip").status_code == 409
    assert snapshot(client)["trucks"][0]["trip_id"] == replacement["id"]


def test_driver_cannot_receive_two_active_trips(client, trip, make_order):
    order = make_order()
    assert assign(client, [order["code"]], truck="camion-2").status_code == 200
    before = dispatch(client)
    assert create_trip(client, truck="camion-2").status_code == 409
    assert dispatch(client) == before
    response = create_trip(client, truck="camion-2", driver="conductor-2")
    assert response.status_code == 201
    assert (
        client.get(f"{ROOT}/driver/trip", headers=OTHER_DRIVER).json()["id"]
        == response.json()["id"]
    )
    assert client.get(f"{ROOT}/driver/trip", headers=DRIVER).json()["id"] == trip["id"]
    assert not any(driver["available"] for driver in dispatch(client)["drivers"])


def test_customer_tracking_excludes_other_stops_and_customer_data(client, trip):
    code, other_code = trip["order_codes"]
    projection = client.get(f"{ROOT}/orders/{code}/tracking", headers=CUSTOMER).json()
    assert projection["status"] == "asignado"
    assert projection["position"] is None
    assert projection["destination"] == trip["stops"][0]["location"]
    assert not (
        {"stops", "order_codes", "contact_phone", "contact_email", "history"} & projection.keys()
    )
    assert other_code not in str(projection)
    assert trip["stops"][1]["address"] not in str(projection)
    assert (
        client.get(
            f"{ROOT}/orders/{code}/tracking", headers={"X-Demo-Actor": "cliente-2"}
        ).status_code
        == 404
    )
    assert client.get(f"{ROOT}/orders/MON-00000000/tracking", headers=CUSTOMER).status_code == 404


def test_tracking_without_trip_and_with_missing_coordinates(client, make_order):
    order = make_order()
    assert (
        client.get(f"{ROOT}/orders/{order['code']}/tracking", headers=CUSTOMER).json()["status"]
        == "sin_viaje"
    )
    assign(client, [order["code"]])
    trip = create_trip(client).json()
    assert trip["route_complete"] is False
    loaded = act(client, trip, "confirm_load").json()
    current = act(client, loaded, "start_trip").json()
    advanced = act(client, current, "advance").json()
    assert advanced["progress_percent"] == 25
    assert advanced["position"] is None
    projection = client.get(f"{ROOT}/orders/{order['code']}/tracking", headers=CUSTOMER).json()
    assert projection["position"] is None
    assert projection["destination"] is None


@pytest.mark.parametrize("actor", ["cliente-1", "cliente-2", "empresa", "unknown"])
def test_driver_routes_reject_other_roles(client, trip, actor):
    headers = {"X-Demo-Actor": actor}
    assert client.get(f"{ROOT}/driver/trip", headers=headers).status_code == 403
    assert client.get(f"{ROOT}/driver/trips/{trip['id']}", headers=headers).status_code == 403
    assert act(client, trip, "confirm_load", actor=actor).status_code == 403


@pytest.mark.parametrize("actor", ["cliente-1", "conductor", "conductor-2", "unknown"])
def test_dispatch_routes_reject_other_roles(client, trip, actor):
    headers = {"X-Demo-Actor": actor}
    assert client.get(f"{ROOT}/company/trips", headers=headers).status_code == 403
    assert (
        client.post(
            f"{ROOT}/company/trips",
            headers=headers,
            json={"truck_id": "camion-2", "driver_id": "conductor", "expected_revision": 1},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{ROOT}/company/trips/{trip['id']}/cancel",
            headers=headers,
            json={"expected_revision": 1},
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"action": "deliver"},
        {"action": "problem"},
        {"progress_percent": 100},
        {"expected_revision": True},
        {"expected_revision": 0},
        {"status": "en_camino"},
    ],
)
def test_invalid_driver_commands_do_not_mutate_trip(client, trip, changes):
    response = client.post(
        f"{ROOT}/driver/trips/{trip['id']}/actions",
        headers=DRIVER,
        json={"action": "confirm_load", "expected_revision": trip["revision"], **changes},
    )
    assert response.status_code == 422
    assert client.get(f"{ROOT}/driver/trip", headers=DRIVER).json() == trip


def test_stale_plans_and_unknown_driver_or_truck_are_rejected(client, make_order):
    order = make_order()
    before = dispatch(client)["revision"]
    assign(client, [order["code"]])
    assert create_trip(client, revision=before).status_code == 409
    assert create_trip(client, driver="cliente-1").status_code == 422
    assert create_trip(client, driver="unknown").status_code == 422
    assert create_trip(client, truck="unknown").status_code == 404
    assert client.get(f"{ROOT}/driver/trips/unknown", headers=DRIVER).status_code == 404
    assert (
        client.post(
            f"{ROOT}/company/trips/unknown/cancel", headers=COMPANY, json={"expected_revision": 1}
        ).status_code
        == 404
    )
    assert dispatch(client)["trips"] == []


def test_simultaneous_cancel_and_departure_apply_only_one_command(client, trip):
    loaded = act(client, trip, "confirm_load").json()
    store = client.app.state.demo_orders

    def apply(command):
        try:
            if command == "cancel":
                store.cancel_trip(
                    trip["id"], RevisionInput(expected_revision=loaded["revision"]), ACTORS[2]
                )
            else:
                store.driver_action(
                    trip["id"],
                    DriverAction(expected_revision=loaded["revision"], action="start_trip"),
                    ACTORS[3],
                )
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(apply, ["cancel", "start"])) == [200, 409]
    state = store.dispatch().trips[0]
    orders = store.list_company()
    if state.status == "en_camino":
        assert all(order.status == "en_camino" and order.trip_id == state.id for order in orders)
    else:
        assert all(order.status == "listo_para_salir" and order.trip_id is None for order in orders)


def test_simultaneous_trip_creation_only_reserves_once(client, make_order):
    order = make_order()
    assign(client, [order["code"]])
    store = client.app.state.demo_orders
    command = TripInput(
        expected_revision=store.dispatch().revision, truck_id="camion-1", driver_id="conductor"
    )

    def apply(_):
        try:
            store.create_trip(command, ACTORS[2])
            return 201
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(apply, range(2))) == [201, 409]
    assert len(store.dispatch().trips) == 1


def test_output_is_a_copy_and_manifests_survive_cancellation(client, trip):
    store = client.app.state.demo_orders
    value = store.driver_trip(ACTORS[3])
    value.stops[0].items[0].quantity = 999
    value.stops[0].location.latitude = 0
    value.order_codes.clear()
    assert store.driver_trip(ACTORS[3]).model_dump(mode="json") == trip
    cancelled = cancel(client, trip).json()
    assign(client, [])
    assert dispatch(client)["trips"][0] == cancelled


def test_trip_contracts_local_mode_and_restart(client, trip):
    paths = client.get("/openapi.json").json()["paths"]
    assert f"{ROOT}/driver/trips/{{trip_id}}/actions" in paths
    assert f"{ROOT}/orders/{{code}}/tracking" in paths
    with TestClient(create_app(Settings(_env_file=None, demo_mode=False))) as disabled:
        assert disabled.get(f"{ROOT}/company/trips", headers=COMPANY).status_code == 404
        assert disabled.get(f"{ROOT}/driver/trip", headers=DRIVER).status_code == 404
    with TestClient(
        create_app(Settings(_env_file=None, demo_mode=True)), client=("203.0.113.1", 50000)
    ) as remote:
        assert remote.get(f"{ROOT}/driver/trip", headers=DRIVER).status_code == 403
    with TestClient(
        create_app(Settings(_env_file=None, demo_mode=True)), client=("127.0.0.1", 50000)
    ) as fresh:
        assert dispatch(fresh)["trips"] == []
        assert fresh.get(f"{ROOT}/driver/trip", headers=DRIVER).json() is None
