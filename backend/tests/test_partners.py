from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from test_fleet import DAY, assign, snapshot
from test_fleet import client as client
from test_fleet import make_order as make_order
from test_incidents import problem, reprogram
from test_trips import act, create_trip

from app.config import Settings
from app.demo import ACTORS
from app.demo_partners import ThirdPartyRequest
from app.main import create_app

ROOT = "/api/v1/demo"
COMPANY = {"X-Demo-Actor": "empresa"}
CUSTOMER = {"X-Demo-Actor": "cliente-1"}


def overview(client):
    response = client.get(f"{ROOT}/company/third-party", headers=COMPANY)
    assert response.status_code == 200
    return response.json()


def request_service(client, order, actor="empresa", **changes):
    return client.post(
        f"{ROOT}/company/orders/{order['code']}/third-party/request",
        headers={"X-Demo-Actor": actor},
        json={
            "expected_revision": order["revision"],
            "partner_id": "aliado-1",
            "reason": "Fuera de la cobertura propia de prueba",
            **changes,
        },
    )


def service_action(client, order, action, actor="empresa", **changes):
    return client.post(
        f"{ROOT}/company/orders/{order['code']}/third-party/actions",
        headers={"X-Demo-Actor": actor},
        json={"expected_revision": order["revision"], "action": action, **changes},
    )


def current(client, code):
    return client.get(f"{ROOT}/company/orders/{code}", headers=COMPANY).json()


def test_empty_catalog_has_only_fictitious_contacts(client):
    data = overview(client)
    assert data["candidates"] == data["services"] == []
    assert len(data["partners"]) == 2
    assert all(partner["contact_email"].endswith(".test") for partner in data["partners"])


def test_candidates_identify_capacity_reservations_and_manual_coverage(client, make_order):
    small = make_order(quantity=3)
    large = make_order(quantity=61)
    by_code = {item["order"]["code"]: item for item in overview(client)["candidates"]}
    assert len(by_code[small["code"]]["compatible_trucks"]) == 3
    assert "revisar la cobertura" in by_code[small["code"]]["fleet_assessment"]
    assert by_code[large["code"]]["compatible_trucks"] == []
    assert "supera la capacidad" in by_code[large["code"]]["fleet_assessment"]
    other_day = DAY + timedelta(days=1)
    for truck in ["camion-1", "camion-2", "camion-3"]:
        reserved = make_order(day=other_day)
        assert assign(client, [reserved["code"]], truck=truck, day=other_day).status_code == 200
    by_code = {item["order"]["code"]: item for item in overview(client)["candidates"]}
    assert by_code[small["code"]]["compatible_trucks"] == []
    assert "reserva" in by_code[small["code"]]["fleet_assessment"]


def test_request_confirm_dispatch_advance_and_customer_tracking(client, make_order):
    original = make_order()
    before_revision = snapshot(client)["revision"]
    response = request_service(client, original)
    assert response.status_code == 200
    pending = response.json()
    service = pending["third_party"]
    assert pending["id"] == original["id"] and pending["code"] == original["code"]
    assert pending["status"] == "listo_para_salir" and pending["delivery_mode"] == "tercero"
    assert service["status"] == "pendiente_aceptacion" and service["partner"]["id"] == "aliado-1"
    assert service["reference"].startswith("TP-")
    assert pending["trip_id"] is pending["assigned_truck_id"] is None
    assert pending["actual_departure_at"] is None
    assert snapshot(client)["revision"] > before_revision
    assert snapshot(client)["ready_orders"] == []
    assert overview(client)["candidates"] == []
    assert overview(client)["services"] == [pending]
    assert service_action(client, pending, "dispatch").status_code == 409
    confirmed = service_action(client, pending, "confirm", note="Aceptación de prueba").json()
    assert confirmed["third_party"]["status"] == "confirmado"
    assert confirmed["third_party"]["confirmed_at"] is not None
    assert confirmed["status"] == "listo_para_salir"
    assert service_action(client, confirmed, "confirm").status_code == 409
    dispatched = service_action(client, confirmed, "dispatch").json()
    assert dispatched["status"] == "en_camino"
    assert dispatched["actual_departure_at"] == dispatched["third_party"]["dispatched_at"]
    assert dispatched["scheduled_departure_at"] == original["scheduled_departure_at"]
    for percent in (25, 50, 75, 100):
        dispatched = service_action(client, dispatched, "advance").json()
        assert dispatched["third_party"]["progress_percent"] == percent
    assert dispatched["delivered_at"] is None and dispatched["status"] == "en_camino"
    assert service_action(client, dispatched, "advance").status_code == 409
    own = client.get(f"{ROOT}/orders/{original['code']}", headers=CUSTOMER).json()
    assert own == dispatched
    assert len(own["third_party"]["history"]) == 7
    assert client.get(f"{ROOT}/driver/trip", headers={"X-Demo-Actor": "conductor"}).json() is None
    tracking = client.get(f"{ROOT}/orders/{original['code']}/tracking", headers=CUSTOMER).json()
    assert tracking["status"] == "en_camino" and tracking["delivery_mode"] == "tercero"
    assert tracking["progress_percent"] == 100
    assert tracking["partner_name"] == service["partner"]["name"]
    assert tracking["service_reference"] == service["reference"]
    assert tracking["position"] is None  # No inventar GPS para un tercero.


@pytest.mark.parametrize("confirm_first", [False, True])
def test_cancel_before_dispatch_preserves_history_and_allows_fleet(
    client, make_order, confirm_first
):
    order = request_service(client, make_order()).json()
    if confirm_first:
        order = service_action(client, order, "confirm").json()
    assert service_action(client, order, "cancel").status_code == 422
    cancelled = service_action(client, order, "cancel", note="Reasignación a flota propia").json()
    assert cancelled["third_party"] is None and cancelled["delivery_mode"] is None
    archive = cancelled["third_party_history"][0]
    assert archive["status"] == "cancelado" and archive["cancelled_at"]
    assert archive["history"][-1]["note"].endswith("Reasignación a flota propia")
    assert snapshot(client)["ready_orders"] == [cancelled]
    assert assign(client, [order["code"]]).status_code == 200
    assert current(client, order["code"])["third_party_history"] == [archive]


def test_cancel_and_request_another_partner_keeps_old_service_independent(client, make_order):
    first = request_service(client, make_order()).json()
    cancelled = service_action(client, first, "cancel", note="Cambio de aliado").json()
    second = request_service(client, cancelled, partner_id="aliado-2").json()
    assert second["third_party"]["partner"]["id"] == "aliado-2"
    assert second["third_party"]["id"] != first["third_party"]["id"]
    confirmed = service_action(client, second, "confirm").json()
    assert confirmed["third_party_history"] == cancelled["third_party_history"]


def test_assigned_orders_require_explicit_release_before_third_party(client, make_order):
    order = make_order()
    assign(client, [order["code"]])
    assigned = current(client, order["code"])
    assert overview(client)["candidates"] == []
    assert request_service(client, assigned).status_code == 409
    trip = create_trip(client).json()
    assert request_service(client, current(client, order["code"])).status_code == 409
    trip = act(client, trip, "confirm_load").json()
    act(client, trip, "start_trip")
    assert request_service(client, current(client, order["code"])).status_code == 409


def test_pending_and_confirmed_services_cannot_be_assigned_or_suggested_or_rescheduled(
    client, make_order
):
    order = request_service(
        client, make_order(location={"latitude": 14.64, "longitude": -90.51})
    ).json()
    for state in ["pendiente_aceptacion", "confirmado"]:
        assert order["third_party"]["status"] == state
        before = current(client, order["code"])
        assert assign(client, [order["code"]]).status_code == 409
        suggestion = client.post(
            f"{ROOT}/company/trucks/camion-1/suggestion",
            headers=COMPANY,
            json={
                "expected_revision": snapshot(client)["revision"],
                "departure_date": DAY.isoformat(),
            },
        )
        assert suggestion.status_code == 200 and suggestion.json()["order_codes"] == []
        scheduled = client.post(
            f"{ROOT}/company/orders/{order['code']}/schedule",
            headers=COMPANY,
            json={
                "expected_revision": order["revision"],
                "scheduled_departure_at": (datetime.now(UTC) + timedelta(days=8)).isoformat(),
            },
        )
        assert scheduled.status_code == 409
        assert current(client, order["code"]) == before
        if state == "pendiente_aceptacion":
            order = service_action(client, order, "confirm").json()


def test_dispatch_forbids_cancel_and_further_changes(client, make_order):
    order = request_service(client, make_order()).json()
    order = service_action(client, order, "confirm").json()
    order = service_action(client, order, "dispatch").json()
    for action in ["dispatch", "confirm", "cancel"]:
        assert service_action(client, order, action, note="Prueba").status_code == 409
    assert request_service(client, order).status_code == 409
    assert current(client, order["code"]) == order


def test_only_ready_orders_can_request_and_ids_must_exist(client, make_order):
    received = make_order(ready=False)
    assert request_service(client, received).status_code == 409
    ready = make_order()
    assert request_service(client, ready, partner_id="inexistente").status_code == 404
    unknown = {**ready, "code": "MON-00000000"}
    assert request_service(client, unknown).status_code == 404
    assert current(client, ready["code"]) == ready


def test_stale_and_repeated_requests_and_actions_do_not_duplicate_history(client, make_order):
    original = make_order()
    pending = request_service(client, original).json()
    assert request_service(client, original).status_code == 409
    assert request_service(client, pending).status_code == 409
    assert service_action(client, original, "confirm").status_code == 409
    confirmed = service_action(client, pending, "confirm").json()
    assert service_action(client, pending, "confirm").status_code == 409
    assert current(client, original["code"]) == confirmed


@pytest.mark.parametrize(
    "actor", ["cliente-1", "cliente-2", "conductor", "conductor-2", "desconocido"]
)
def test_company_only_and_customer_ownership(client, make_order, actor):
    order = make_order()
    assert (
        client.get(f"{ROOT}/company/third-party", headers={"X-Demo-Actor": actor}).status_code
        == 403
    )
    assert request_service(client, order, actor=actor).status_code == 403
    assert service_action(client, order, "confirm", actor=actor).status_code == 403
    pending = request_service(client, order).json()
    assert (
        client.get(
            f"{ROOT}/orders/{order['code']}", headers={"X-Demo-Actor": "cliente-2"}
        ).status_code
        == 404
    )
    assert pending["third_party"] is not None


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": " "},
        {"reason": "x" * 1001},
        {"expected_revision": True},
        {"expected_revision": 0},
        {"status": "confirmado"},
        {"partner_id": ""},
        {"progress_percent": 100},
        {"delivery_mode": "flota_propia"},
    ],
)
def test_invalid_request_cannot_forge_server_fields(client, make_order, changes):
    order = make_order()
    assert request_service(client, order, **changes).status_code == 422
    assert current(client, order["code"]) == order


@pytest.mark.parametrize(
    "changes",
    [
        {"action": "delivered"},
        {"action": "cancel", "note": " "},
        {"expected_revision": True},
        {"progress_percent": 100},
        {"note": "x" * 1001},
    ],
)
def test_invalid_action_is_atomic(client, make_order, changes):
    pending = request_service(client, make_order()).json()
    data = {"action": "confirm", **changes}
    assert service_action(client, pending, **data).status_code == 422
    assert current(client, pending["code"]) == pending


def test_assignment_racing_request_has_one_winner(client, make_order):
    order = make_order()
    revision = snapshot(client)["revision"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(request_service, client, order),
            executor.submit(assign, client, [order["code"]], revision=revision),
        ]
        assert sorted(f.result().status_code for f in futures) == [200, 409]
    result = current(client, order["code"])
    assert bool(result["third_party"]) != bool(result["assigned_truck_id"])


def test_confirm_racing_cancel_has_one_winner(client, make_order):
    order = request_service(client, make_order()).json()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(service_action, client, order, "confirm"),
            executor.submit(service_action, client, order, "cancel", note="Cambio"),
        ]
        assert sorted(f.result().status_code for f in futures) == [200, 409]
    result = current(client, order["code"])
    assert result["revision"] == order["revision"] + 1


def test_reprogrammed_order_can_use_partner_and_old_trip_cannot_touch_it(client, make_order):
    first = make_order(location={"latitude": 14.64, "longitude": -90.51})
    second = make_order(location={"latitude": 14.7, "longitude": -90.6})
    assign(client, [first["code"], second["code"]])
    trip = create_trip(client).json()
    for command in ("confirm_load", "start_trip", "advance"):
        trip = act(client, trip, command).json()
    trip = problem(client, trip).json()
    ready = reprogram(client, trip).json()
    pending = request_service(client, ready).json()
    assert pending["third_party"] is not None
    trip = client.get(
        f"{ROOT}/driver/trips/{trip['id']}", headers={"X-Demo-Actor": "conductor"}
    ).json()
    assert act(client, trip, "advance").status_code == 200
    assert current(client, first["code"]) == pending
    assert len(pending["delivery_attempts"]) == 1
    assert pending["delivery_attempts"][0]["status"] == "reprogramado"


def test_dispatch_racing_cancel_has_one_winner(client, make_order):
    pending = request_service(client, make_order()).json()
    order = service_action(client, pending, "confirm").json()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(service_action, client, order, "dispatch"),
            executor.submit(service_action, client, order, "cancel", note="Cambio"),
        ]
        assert sorted(f.result().status_code for f in futures) == [200, 409]
    result = current(client, order["code"])
    if result["third_party"]:
        assert result["status"] == "en_camino" and result["actual_departure_at"]
    else:
        assert result["status"] == "listo_para_salir" and result["actual_departure_at"] is None


def test_projections_and_partner_snapshots_do_not_mutate_storage(client, make_order):
    order = make_order()
    store = client.app.state.demo_orders
    output = store.request_third_party(
        order["code"],
        ThirdPartyRequest(
            expected_revision=order["revision"], partner_id="aliado-1", reason="Fuera de cobertura"
        ),
        ACTORS[2],
    )
    output.third_party.partner.name = "Alterado"
    output.third_party.history.clear()
    view = store.third_party_snapshot()
    view.services[0].third_party.partner.name = "Alterado otra vez"
    view.partners[0].name = "Otro"
    actual = current(client, order["code"])
    assert actual["third_party"]["partner"]["name"] == "PaqueteríaTest"
    assert len(actual["third_party"]["history"]) == 1
    assert overview(client)["partners"][0]["name"] == "PaqueteríaTest"


def test_third_party_routes_are_local_and_disabled_without_demo():
    with TestClient(
        create_app(Settings(_env_file=None, demo_mode=True)), client=("192.0.2.1", 50000)
    ) as remote:
        assert remote.get(f"{ROOT}/company/third-party", headers=COMPANY).status_code == 403
    with TestClient(create_app(Settings(_env_file=None, demo_mode=False))) as real:
        assert real.get(f"{ROOT}/company/third-party", headers=COMPANY).status_code == 404
        assert not any("third-party" in path for path in real.get("/openapi.json").json()["paths"])
