from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_fleet import DAY, GUATEMALA, assign, snapshot
from test_fleet import client as client
from test_fleet import make_order as make_order
from test_trips import act, create_trip
from test_trips import trip as trip

from app.config import Settings
from app.demo import ACTORS, RevisionInput
from app.demo_incidents import IncidentInput, RescheduleInput
from app.demo_trips import DriverAction
from app.main import create_app

ROOT = "/api/v1/demo"
COMPANY = {"X-Demo-Actor": "empresa"}
DRIVER = {"X-Demo-Actor": "conductor"}
CUSTOMER = {"X-Demo-Actor": "cliente-1"}
NEXT_DAY = DAY + timedelta(days=2)


@pytest.fixture
def on_road(client, trip):
    loaded = act(client, trip, "confirm_load").json()
    return act(client, loaded, "start_trip").json()


def read_trip(client, trip_id):
    return next(
        trip
        for trip in client.get(f"{ROOT}/company/trips", headers=COMPANY).json()["trips"]
        if trip["id"] == trip_id
    )


def report(client, trip, actor="empresa", **changes):
    branch = "company" if actor == "empresa" else "driver"
    return client.post(
        f"{ROOT}/{branch}/trips/{trip['id']}/incidents",
        headers={"X-Demo-Actor": actor},
        json={
            "expected_revision": trip["revision"],
            "kind": "bloqueo",
            "reason": "Bloqueo de prueba",
            **changes,
        },
    )


def preview(client, trip, incident_id=None):
    incident_id = incident_id or trip["active_incident_id"]
    return client.post(
        f"{ROOT}/company/trips/{trip['id']}/incidents/{incident_id}/alternative",
        headers=COMPANY,
        json={"expected_revision": trip["revision"]},
    )


def resolve(client, trip, **changes):
    return client.post(
        f"{ROOT}/company/trips/{trip['id']}/incidents/{trip['active_incident_id']}/resolve",
        headers=COMPANY,
        json={
            "expected_revision": trip["revision"],
            "decision": "alternativa",
            "delay_minutes": 30,
            "resolution_note": "Desvío de prueba aprobado",
            **changes,
        },
    )


def problem(client, trip, index=0, actor="conductor", **changes):
    stop = trip["stops"][index]
    return client.post(
        f"{ROOT}/driver/trips/{trip['id']}/orders/{stop['code']}/problem",
        headers={"X-Demo-Actor": actor},
        json={
            "expected_revision": trip["revision"],
            "expected_order_revision": stop["order_revision"],
            "reason": "Destinatario ausente",
            **changes,
        },
    )


def reprogram(client, trip, index=0, **changes):
    stop = trip["stops"][index]
    departure = datetime.combine(NEXT_DAY, time(9), tzinfo=GUATEMALA)
    return client.post(
        f"{ROOT}/company/orders/{stop['code']}/reschedule",
        headers=COMPANY,
        json={
            "expected_revision": stop["order_revision"],
            "expected_trip_revision": trip["revision"],
            "scheduled_departure_at": departure.isoformat(),
            "estimated_delivery_at": (departure + timedelta(hours=5)).isoformat(),
            "resolution_note": "Destinatario confirma nueva fecha",
            **changes,
        },
    )


@pytest.mark.parametrize("actor", ["empresa", "conductor"])
def test_incident_pauses_advance_and_alerts_customer_without_exposing_route(client, on_road, actor):
    advanced = act(client, on_road, "advance").json()
    response = report(client, advanced, actor=actor)
    assert response.status_code == 200
    blocked = response.json()
    assert blocked["progress_percent"] == 25
    assert blocked["position"] == advanced["position"]
    assert blocked["incidents"][0]["status"] == "abierto"
    assert act(client, blocked, "advance").status_code == 409
    assert report(client, blocked).status_code == 409
    tracking = client.get(
        f"{ROOT}/orders/{blocked['order_codes'][0]}/tracking", headers=CUSTOMER
    ).json()
    assert tracking["incident_message"] is not None
    assert tracking["position"] == blocked["position"]
    assert not ({"incidents", "route_points", "stops", "order_codes"} & tracking.keys())
    assert blocked["order_codes"][1] not in str(tracking)


def test_alternative_preview_is_read_only_and_approval_preserves_position(client, on_road):
    advanced = act(client, on_road, "advance").json()
    blocked = report(client, advanced).json()
    before = read_trip(client, blocked["id"])
    response = preview(client, blocked)
    assert response.status_code == 200
    proposal = response.json()
    assert proposal["points"][0] == blocked["position"]
    assert len(proposal["points"]) >= 3
    assert read_trip(client, blocked["id"]) == before
    resolved = resolve(client, blocked).json()
    assert resolved["active_incident_id"] is None
    assert resolved["progress_percent"] == blocked["progress_percent"]
    assert resolved["position"] == blocked["position"]
    assert resolved["route_points"] == proposal["points"]
    assert resolved["route_start_percent"] == 25
    assert resolved["incidents"][0]["alternative"] == proposal["points"]
    assert act(client, resolved, "advance").status_code == 200
    for code in resolved["order_codes"]:
        order = client.get(f"{ROOT}/orders/{code}", headers=CUSTOMER).json()
        assert datetime.fromisoformat(order["estimated_delivery_at"]) > datetime.now(UTC)
        assert order["status"] == "en_camino"
    assert resolve(client, blocked).status_code == 409


def test_resolving_second_incident_adds_delay_to_existing_estimate(client, on_road):
    first = resolve(client, report(client, on_road).json()).json()
    code = first["order_codes"][0]
    old_eta = client.get(f"{ROOT}/orders/{code}", headers=CUSTOMER).json()["estimated_delivery_at"]
    blocked = report(client, first, kind="accidente").json()
    result = resolve(client, blocked, decision="continuar", delay_minutes=15)
    assert result.status_code == 200
    current = result.json()
    assert len(current["incidents"]) == 2
    assert current["incidents"][0]["decision"] == "alternativa"
    assert current["incidents"][1]["decision"] == "continuar"
    eta = client.get(f"{ROOT}/orders/{code}", headers=CUSTOMER).json()["estimated_delivery_at"]
    assert datetime.fromisoformat(eta) == datetime.fromisoformat(old_eta) + timedelta(minutes=15)


def test_incomplete_route_can_be_resolved_without_inventing_coordinates(client, make_order):
    order = make_order()
    assign(client, [order["code"]])
    assigned = create_trip(client).json()
    loaded = act(client, assigned, "confirm_load").json()
    started = act(client, loaded, "start_trip").json()
    blocked = report(client, started).json()
    assert preview(client, blocked).status_code == 409
    assert resolve(client, blocked).status_code == 409
    assert read_trip(client, blocked["id"]) == blocked
    result = resolve(client, blocked, decision="continuar", delay_minutes=0)
    assert result.status_code == 200
    advanced = act(client, result.json(), "advance").json()
    assert advanced["position"] is None
    assert advanced["route_complete"] is False


def test_failed_attempt_and_partial_reschedule_keep_identity_and_other_order(client, on_road):
    failed = problem(client, on_road).json()
    assert failed["stops"][0]["delivery_status"] == "con_problema"
    assert problem(client, failed).status_code == 409
    code = failed["order_codes"][0]
    original = client.get(f"{ROOT}/orders/{code}", headers=CUSTOMER).json()
    other_code = failed["order_codes"][1]
    other_before = client.get(f"{ROOT}/orders/{other_code}", headers=CUSTOMER).json()
    response = reprogram(client, failed)
    assert response.status_code == 200
    order = response.json()
    for field in ("id", "code", "created_at", "customer_id", "items", "address"):
        assert order[field] == original[field]
    assert order["status"] == "listo_para_salir" and order["needs_reschedule"] is False
    assert order["trip_id"] is None and order["assigned_truck_id"] is None
    assert order["delivery_mode"] is None and order["actual_departure_at"] is None
    assert order["delivered_at"] is None
    attempt = order["delivery_attempts"][0]
    assert attempt["reason"] == "Destinatario ausente"
    assert (
        attempt["status"] == "reprogramado"
        and attempt["actual_departure_at"] == failed["actual_departure_at"]
    )
    assert attempt["scheduled_departure_at"] == order["scheduled_departure_at"]
    current = read_trip(client, failed["id"])
    assert current["status"] == "en_camino"
    assert current["stops"][0]["delivery_status"] == "reprogramado"
    assert snapshot(client)["trucks"][0]["used_capacity"] == 3
    assert client.get(f"{ROOT}/orders/{other_code}", headers=CUSTOMER).json() == other_before
    assert reprogram(client, current).status_code == 409


def test_original_trip_cannot_change_rescheduled_order_in_new_trip(client, on_road):
    failed = problem(client, on_road).json()
    order = reprogram(client, failed).json()
    assign(client, [order["code"]], truck="camion-2", day=NEXT_DAY)
    assigned = create_trip(client, truck="camion-2", driver="conductor-2").json()
    loaded = act(client, assigned, "confirm_load", actor="conductor-2").json()
    started = act(client, loaded, "start_trip", actor="conductor-2").json()
    before = client.get(f"{ROOT}/orders/{order['code']}", headers=CUSTOMER).json()
    current_original = read_trip(client, on_road["id"])
    assert act(client, current_original, "advance").status_code == 200
    blocked_original = report(client, read_trip(client, on_road["id"])).json()
    assert resolve(client, blocked_original, decision="continuar").status_code == 200
    assert client.get(f"{ROOT}/orders/{order['code']}", headers=CUSTOMER).json() == before
    failed_again = problem(client, started, actor="conductor-2").json()
    response = reprogram(client, failed_again)
    assert response.status_code == 200
    attempts = response.json()["delivery_attempts"]
    assert len(attempts) == 2 and attempts[0]["trip_id"] != attempts[1]["trip_id"]
    assert all(attempt["status"] == "reprogramado" for attempt in attempts)


def test_all_orders_rescheduled_release_trip_driver_and_truck(client, on_road):
    current = report(client, on_road).json()
    for index in range(2):
        current = problem(client, current, index=index).json()
        assert reprogram(client, current, index=index).status_code == 200
        current = read_trip(client, on_road["id"])
    assert current["status"] == "reprogramado"
    assert current["active_incident_id"] is None
    assert current["incidents"][0]["decision"] == "reprogramado"
    assert client.get(f"{ROOT}/driver/trip", headers=DRIVER).json() is None
    truck = snapshot(client)["trucks"][0]
    assert truck["availability"] == "disponible" and truck["trip_id"] is None
    assert truck["order_codes"] == []
    assert act(client, current, "advance").status_code == 409
    assign(client, current["order_codes"], day=NEXT_DAY)
    assert create_trip(client).status_code == 201


@pytest.mark.parametrize(
    "changes",
    [{"kind": "otro"}, {"reason": "  "}, {"reason": "x" * 1001}, {"expected_revision": True}],
)
def test_invalid_incident_inputs_leave_trip_unchanged(client, on_road, changes):
    assert report(client, on_road, **changes).status_code == 422
    assert read_trip(client, on_road["id"]) == on_road


@pytest.mark.parametrize(
    "changes",
    [
        {"delay_minutes": -1},
        {"delay_minutes": True},
        {"delay_minutes": 1441},
        {"resolution_note": " "},
        {"decision": "entregado"},
    ],
)
def test_invalid_resolution_does_not_resume_or_change_estimates(client, on_road, changes):
    blocked = report(client, on_road).json()
    assert resolve(client, blocked, **changes).status_code == 422
    assert read_trip(client, on_road["id"]) == blocked


@pytest.mark.parametrize(
    "changes",
    [
        {"scheduled_departure_at": "2000-01-01T00:00:00Z"},
        {"estimated_delivery_at": "2000-01-01T00:00:00Z"},
        {"scheduled_departure_at": "2035-01-01T12:00:00"},
        {"resolution_note": " "},
        {"expected_trip_revision": True},
        {"expected_revision": True},
        {"status": "entregado"},
    ],
)
def test_invalid_reschedule_keeps_assignment_attempt_and_dates(client, on_road, changes):
    failed = problem(client, on_road).json()
    before = client.get(f"{ROOT}/orders/{failed['order_codes'][0]}", headers=CUSTOMER).json()
    assert reprogram(client, failed, **changes).status_code == 422
    assert read_trip(client, on_road["id"]) == failed
    assert (
        client.get(f"{ROOT}/orders/{failed['order_codes'][0]}", headers=CUSTOMER).json() == before
    )


def test_state_and_revision_guards(client, trip, on_road):
    assert report(client, trip).status_code == 409
    assert problem(client, trip).status_code == 409
    assert reprogram(client, on_road).status_code == 409
    assert preview(client, on_road, incident_id="unknown").status_code == 404
    failed = problem(client, on_road).json()
    assert reprogram(client, on_road).status_code == 409
    assert reprogram(client, failed, expected_trip_revision=1).status_code == 409
    assert problem(client, failed, expected_order_revision=1).status_code == 409
    blocked = report(client, failed).json()
    assert preview(client, failed, incident_id=blocked["active_incident_id"]).status_code == 409


@pytest.mark.parametrize("actor", ["cliente-1", "conductor", "conductor-2", "unknown"])
def test_company_incident_and_reschedule_routes_reject_other_roles(client, on_road, actor):
    headers = {"X-Demo-Actor": actor}
    path = f"{ROOT}/company/trips/{on_road['id']}/incidents"
    assert (
        client.post(
            path,
            headers=headers,
            json={"expected_revision": on_road["revision"], "kind": "bloqueo", "reason": "Prueba"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            path + "/unknown/alternative", headers=headers, json={"expected_revision": 1}
        ).status_code
        == 403
    )
    assert (
        client.post(
            path + "/unknown/resolve",
            headers=headers,
            json={
                "expected_revision": 1,
                "decision": "continuar",
                "delay_minutes": 0,
                "resolution_note": "Resuelto",
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{ROOT}/company/orders/{on_road['order_codes'][0]}/reschedule",
            headers=headers,
            json={
                "expected_revision": 1,
                "expected_trip_revision": 1,
                "resolution_note": "Nueva fecha",
                "scheduled_departure_at": datetime.combine(
                    NEXT_DAY, time(9), tzinfo=GUATEMALA
                ).isoformat(),
            },
        ).status_code
        == 403
    )


def test_driver_ownership_and_problem_scope(client, on_road, make_order):
    assert report(client, on_road, actor="conductor-2").status_code == 404
    assert problem(client, on_road, actor="conductor-2").status_code == 404
    assert problem(client, on_road, actor="empresa").status_code == 403
    other = make_order()
    stop = on_road["stops"][0]
    assert (
        client.post(
            f"{ROOT}/driver/trips/{on_road['id']}/orders/{other['code']}/problem",
            headers=DRIVER,
            json={
                "expected_revision": on_road["revision"],
                "expected_order_revision": stop["order_revision"],
                "reason": "No pertenece",
            },
        ).status_code
        == 404
    )


def test_incident_at_end_is_rejected_but_failed_attempt_can_be_reprogrammed(client, on_road):
    current = on_road
    for _ in range(4):
        current = act(client, current, "advance").json()
    assert report(client, current).status_code == 409
    failed = problem(client, current).json()
    assert reprogram(client, failed).status_code == 200
    assert read_trip(client, current["id"])["progress_percent"] == 100


def test_racing_incident_and_advance_only_apply_one_change(client, on_road):
    store = client.app.state.demo_orders

    def apply(command):
        try:
            if command == "incident":
                store.report_incident(
                    on_road["id"],
                    IncidentInput(
                        expected_revision=on_road["revision"], kind="bloqueo", reason="Prueba"
                    ),
                    ACTORS[2],
                )
            else:
                store.driver_action(
                    on_road["id"],
                    DriverAction(expected_revision=on_road["revision"], action="advance"),
                    ACTORS[3],
                )
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(apply, ["incident", "advance"])) == [200, 409]
    current = read_trip(client, on_road["id"])
    assert (current["progress_percent"], bool(current["active_incident_id"])) in (
        (0, True),
        (25, False),
    )


def test_racing_reschedule_and_advance_cannot_corrupt_released_order(client, on_road):
    failed = problem(client, on_road).json()
    store = client.app.state.demo_orders
    stop = failed["stops"][0]

    def apply(command):
        try:
            if command == "reschedule":
                store.reschedule(
                    stop["code"],
                    RescheduleInput(
                        expected_revision=stop["order_revision"],
                        expected_trip_revision=failed["revision"],
                        scheduled_departure_at=datetime.combine(
                            NEXT_DAY, time(9), tzinfo=GUATEMALA
                        ),
                        resolution_note="Nueva fecha",
                    ),
                    ACTORS[2],
                )
            else:
                store.driver_action(
                    failed["id"],
                    DriverAction(expected_revision=failed["revision"], action="advance"),
                    ACTORS[3],
                )
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(apply, ["reschedule", "advance"])) == [200, 409]
    order = store.get_company(stop["code"])
    assert (order.status == "listo_para_salir" and order.trip_id is None) or (
        order.status == "en_camino" and order.needs_reschedule
    )


def test_projections_are_copies_and_mode_boundaries_remain(client, on_road):
    blocked = report(client, on_road).json()
    store = client.app.state.demo_orders
    projection = store.driver_trip(ACTORS[3])
    projection.route_points[0].latitude = 0
    projection.incidents[0].route_before[0].latitude = 0
    proposal = store.alternative(
        blocked["id"],
        blocked["active_incident_id"],
        RevisionInput(expected_revision=blocked["revision"]),
    )
    proposal.points[0].latitude = 0
    assert read_trip(client, blocked["id"]) == blocked
    with TestClient(create_app(Settings(_env_file=None, demo_mode=False))) as disabled:
        assert (
            disabled.post(f"{ROOT}/company/trips/unknown/incidents", headers=COMPANY).status_code
            == 404
        )
    with TestClient(
        create_app(Settings(_env_file=None, demo_mode=True)), client=("203.0.113.1", 50000)
    ) as remote:
        assert (
            remote.post(
                f"{ROOT}/driver/trips/unknown/incidents",
                headers=DRIVER,
                json={"expected_revision": 1, "kind": "bloqueo", "reason": "Prueba"},
            ).status_code
            == 403
        )
