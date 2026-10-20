"""Persistencia del agregado de demo. Cada operación usa una transacción PostgreSQL."""

import json
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import Engine, select, text, update

from app.demo import OrderOutput
from app.demo_deliveries import DemoDeliveryStore
from app.demo_fleet import TruckPlan
from app.demo_trips import TripState
from app.models import SCHEMA_REVISION, PitchScenario, PitchSession

request_generation: ContextVar[str | None] = ContextVar("pitch_generation", default=None)
MAX_PITCH_ORDERS = 100
MAX_PAYLOAD_BYTES = 2_000_000
MUTATIONS = {
    "create",
    "correct",
    "act",
    "schedule",
    "assign",
    "create_trip",
    "cancel_trip",
    "driver_action",
    "report_incident",
    "resolve_incident",
    "report_problem",
    "reschedule",
    "request_third_party",
    "third_party_action",
    "deliver_order",
}
READS = {
    "list_for",
    "get_for",
    "list_company",
    "get_company",
    "planning",
    "suggest",
    "dispatch",
    "driver_trip",
    "driver_closed_trips",
    "tracking",
    "alternative",
    "third_party_snapshot",
}


class StoredRequest(BaseModel):
    actor_id: str
    key: str
    fingerprint: str
    code: str


class ScenarioState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    planning_revision: int = Field(ge=1)
    orders: list[OrderOutput]
    trucks: list[TruckPlan]
    trips: list[TripState]
    requests: list[StoredRequest]


def dump_store(store: DemoDeliveryStore) -> dict:
    return ScenarioState(
        planning_revision=store._planning_revision,
        orders=list(store._orders.values()),
        trucks=list(store._trucks.values()),
        trips=list(store._trips.values()),
        requests=[
            StoredRequest(actor_id=actor, key=key, fingerprint=value[0], code=value[1])
            for (actor, key), value in store._requests.items()
        ],
    ).model_dump(mode="json")


def load_store(payload: dict) -> DemoDeliveryStore:
    try:
        state = ScenarioState.model_validate(payload)
    except ValidationError:
        raise HTTPException(503, "Versión del escenario no disponible; revisar migración") from None
    store = DemoDeliveryStore()
    store._planning_revision = state.planning_revision
    store._orders = {order.code: order for order in state.orders}
    store._trucks = {truck.id: truck for truck in state.trucks}
    store._trips = {trip.id: trip for trip in state.trips}
    store._requests = {
        (item.actor_id, item.key): (item.fingerprint, item.code) for item in state.requests
    }
    return store


def check_schema(connection) -> None:
    revision = connection.scalar(text("SELECT version_num FROM public.monami_schema_version"))
    if revision != SCHEMA_REVISION:
        raise HTTPException(503, "Aplicar las migraciones antes de utilizar el pitch")
    connection.execute(select(PitchSession).limit(0))


def scenario_row(connection, scenario_id: str, *, lock: bool = False):
    statement = select(PitchScenario).where(PitchScenario.id == scenario_id)
    if lock:
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '15s'"))
        statement = statement.with_for_update()
    row = connection.execute(statement).mappings().first()
    if row is None:
        raise HTTPException(503, "Cargar explícitamente el escenario con app.pitch_seed")
    return row


class PersistentDemoStore:
    def __init__(self, engine: Engine, scenario_id: str):
        self.engine, self.scenario_id = engine, scenario_id

    def metadata(self) -> dict:
        with self.engine.connect() as connection:
            check_schema(connection)
            row = scenario_row(connection, self.scenario_id)
            load_store(row["payload"])
            return {
                "scenario_generation": str(row["generation"]),
                "scenario_name": "Monami · Pitch preparado",
            }

    def __getattr__(self, method: str):
        if method not in MUTATIONS | READS:
            raise AttributeError(method)

        def operation(*args, **kwargs):
            with self.engine.begin() as connection:
                row = scenario_row(connection, self.scenario_id, lock=True)
                if method in MUTATIONS and request_generation.get() != str(row["generation"]):
                    raise HTTPException(
                        409, "El escenario se reinició. Recarga la demo antes de continuar"
                    )
                store = load_store(row["payload"])
                if method == "create" and len(store._orders) >= MAX_PITCH_ORDERS:
                    actor, _, key = args
                    if (actor.id, key) not in store._requests:
                        raise HTTPException(
                            409, "La demo admite 100 pedidos; reinicia el escenario para continuar"
                        )
                result = getattr(store, method)(*args, **kwargs)
                if method in MUTATIONS:
                    payload = dump_store(store)
                    if len(json.dumps(payload).encode()) > MAX_PAYLOAD_BYTES:
                        raise HTTPException(
                            409, "El escenario alcanzó su límite; reinicia la presentación"
                        )
                    connection.execute(
                        update(PitchScenario)
                        .where(PitchScenario.id == self.scenario_id)
                        .values(payload=payload, updated_at=datetime.now(UTC))
                    )
                return result

        return operation
