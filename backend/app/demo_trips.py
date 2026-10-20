"""Viajes locales: manifiesto, carga, salida y posición simulada compartida."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.demo import (
    ACTORS,
    Company,
    Customer,
    DemoActor,
    LocalDemo,
    Location,
    OrderItem,
    OrderStatus,
    RevisionInput,
)
from app.demo_fleet import DEPOT, DemoPlanningStore, TruckOutput, distance_km, load_units
from app.models import Role

trip_router = APIRouter(prefix="/api/v1/demo", tags=["viajes locales"])
TripStatus = Literal[
    "asignado", "carga_confirmada", "en_camino", "cancelado", "reprogramado", "completado"
]
ACTIVE_TRIP_STATUSES = ("asignado", "carga_confirmada", "en_camino")


class TripStop(BaseModel):
    position: int
    code: str
    address: str
    location: Location | None
    load_units: int
    items: list[OrderItem]
    contact_name: str
    contact_email: str
    contact_phone: str
    instructions: str
    order_revision: int = 1
    delivery_status: Literal["pendiente", "con_problema", "reprogramado", "entregado"] = "pendiente"
    delivered_at: datetime | None = None
    problem_reason: str = ""
    rescheduled_departure_at: datetime | None = None
    estimated_delivery_at: datetime | None = None


class RouteIncident(BaseModel):
    id: str
    kind: Literal["bloqueo", "accidente"]
    reason: str
    reported_by: str
    reported_at: datetime
    progress_percent: int
    position: Location | None
    status: Literal["abierto", "resuelto"] = "abierto"
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    decision: Literal["alternativa", "continuar", "reprogramado"] | None = None
    resolution_note: str = ""
    delay_minutes: int = 0
    route_before: list[Location | None] = Field(default_factory=list)
    alternative: list[Location] | None = None


class TripEvent(BaseModel):
    action: str
    actor_name: str
    at: datetime
    progress_percent: int


class TripState(BaseModel):
    id: str
    revision: int = 1
    truck_id: str
    truck_name: str
    driver_id: str
    driver_name: str
    capacity: int
    load_units: int
    order_codes: list[str]
    stops: list[TripStop]
    status: TripStatus = "asignado"
    created_at: datetime
    planned_departure_at: datetime
    actual_departure_at: datetime | None = None
    closed_at: datetime | None = None
    progress_percent: int = 0
    history: list[TripEvent] = Field(default_factory=list)
    incidents: list[RouteIncident] = Field(default_factory=list)
    active_incident_id: str | None = None
    excluded_order_codes: list[str] = Field(default_factory=list)
    completed_order_codes: list[str] = Field(default_factory=list)
    route_points: list[Location | None] = Field(default_factory=list)
    route_start_percent: int = 0


class TripOutput(TripState):
    depot: Location = DEPOT
    position: Location | None
    route_complete: bool


class DriverAvailability(DemoActor):
    available: bool


class DispatchSnapshot(BaseModel):
    revision: int
    drivers: list[DriverAvailability]
    dispatchable_trucks: list[TruckOutput]
    trips: list[TripOutput]


class TripInput(RevisionInput):
    truck_id: str = Field(min_length=1, max_length=80)
    driver_id: str = Field(min_length=1, max_length=80)


class DriverAction(RevisionInput):
    action: Literal["confirm_load", "start_trip", "advance"]


class CustomerTracking(BaseModel):
    code: str
    status: TripStatus | Literal["sin_viaje", "pendiente_aceptacion", "confirmado", "entregado"]
    revision: int
    delivery_mode: Literal["flota_propia", "tercero"] | None = None
    partner_name: str | None = None
    service_reference: str | None = None
    truck_name: str | None = None
    driver_name: str | None = None
    actual_departure_at: datetime | None = None
    delivered_at: datetime | None = None
    progress_percent: int = 0
    position: Location | None = None
    depot: Location = DEPOT
    destination: Location | None = None
    route_complete: bool = False
    incident_message: str | None = None
    estimated_delivery_at: datetime | None = None
    needs_reschedule: bool = False


def active_codes(trip: TripState) -> list[str]:
    return [
        code
        for code in trip.order_codes
        if code not in trip.excluded_order_codes and code not in trip.completed_order_codes
    ]


def route_points(trip: TripState) -> list[Location | None]:
    return trip.route_points or [
        DEPOT,
        *(stop.location for stop in trip.stops if stop.code in active_codes(trip)),
    ]


def simulated_position(trip: TripState) -> Location | None:
    if trip.status != "en_camino":
        return None
    points = route_points(trip)
    if trip.progress_percent == trip.route_start_percent:
        return points[0].model_copy(deep=True) if points[0] else None
    if any(point is None for point in points):
        return None
    if trip.progress_percent == 100:
        return points[-1].model_copy(deep=True)
    lengths = [distance_km(a, b) for a, b in zip(points, points[1:], strict=False)]
    fraction_done = (trip.progress_percent - trip.route_start_percent) / (
        100 - trip.route_start_percent
    )
    remaining = sum(lengths) * fraction_done
    for start, end, length in zip(points, points[1:], lengths, strict=False):
        if length > 0 and remaining < length:
            fraction = remaining / length
            longitude_delta = (end.longitude - start.longitude + 180) % 360 - 180
            return Location(
                latitude=start.latitude + (end.latitude - start.latitude) * fraction,
                longitude=(start.longitude + longitude_delta * fraction + 180) % 360 - 180,
            )
        remaining -= length
    return points[-1].model_copy(deep=True)


class DemoTripStore(DemoPlanningStore):
    def __init__(self) -> None:
        super().__init__()
        self._trips: dict[str, TripState] = {}

    def _trip(self, trip_id: str, actor: DemoActor | None = None) -> TripState:
        trip = self._trips.get(trip_id)
        if trip is None or (actor is not None and trip.driver_id != actor.id):
            raise HTTPException(404, "Viaje no encontrado para este perfil")
        return trip

    def _output(self, trip: TripState) -> TripOutput:
        data = trip.model_dump()
        data["route_points"] = [
            point.model_copy(deep=True) if point else None for point in route_points(trip)
        ]
        output = TripOutput(
            **data,
            position=simulated_position(trip),
            route_complete=all(point is not None for point in route_points(trip)),
        )
        for stop in output.stops:
            order = self._orders[stop.code]
            attempt = next(
                (
                    attempt
                    for attempt in reversed(order.delivery_attempts)
                    if attempt.trip_id == trip.id
                ),
                None,
            )
            if stop.code in trip.excluded_order_codes:
                stop.delivery_status = "reprogramado"
                if attempt:
                    stop.problem_reason = attempt.reason
                    stop.rescheduled_departure_at = attempt.scheduled_departure_at
                    stop.estimated_delivery_at = attempt.estimated_delivery_at
            elif order.trip_id == trip.id:
                stop.order_revision = order.revision
                stop.delivery_status = (
                    "entregado"
                    if stop.code in trip.completed_order_codes
                    else "con_problema"
                    if order.needs_reschedule
                    else "pendiente"
                )
                stop.delivered_at = order.delivered_at
                stop.problem_reason = attempt.reason if order.needs_reschedule and attempt else ""
                stop.estimated_delivery_at = order.estimated_delivery_at
        return output

    def _finish_if_resolved(self, trip: TripState, actor: DemoActor) -> None:
        if active_codes(trip) or trip.status != "en_camino":
            return
        position = simulated_position(trip)
        now = datetime.now(UTC)
        if trip.active_incident_id:
            incident = next(item for item in trip.incidents if item.id == trip.active_incident_id)
            incident.status, incident.resolved_by, incident.resolved_at = (
                "resuelto",
                actor.name,
                now,
            )
            incident.decision = "reprogramado"
            incident.resolution_note = "No quedan pedidos pendientes en este viaje"
        trip.active_incident_id = None
        trip.status = "completado" if trip.completed_order_codes else "reprogramado"
        trip.closed_at = now
        trip.route_points = [position]
        self._truck(trip.truck_id).trip_id = None
        self._event(trip, actor, "Viaje cerrado: pedidos entregados o reprogramados")

    @staticmethod
    def _event(trip: TripState, actor: DemoActor, action: str) -> None:
        trip.history.append(
            TripEvent(
                action=action,
                actor_name=actor.name,
                at=datetime.now(UTC),
                progress_percent=trip.progress_percent,
            )
        )

    def dispatch(self) -> DispatchSnapshot:
        with self._lock:
            busy = {
                trip.driver_id
                for trip in self._trips.values()
                if trip.status in ACTIVE_TRIP_STATUSES
            }
            return DispatchSnapshot(
                revision=self._planning_revision,
                drivers=[
                    DriverAvailability(**actor.model_dump(), available=actor.id not in busy)
                    for actor in ACTORS
                    if actor.role == Role.DRIVER
                ],
                dispatchable_trucks=[
                    self._truck_output(truck)
                    for truck in self._trucks.values()
                    if truck.order_codes and not truck.trip_id
                ],
                trips=[self._output(trip) for trip in reversed(list(self._trips.values()))],
            )

    def create_trip(self, data: TripInput, actor: DemoActor) -> TripOutput:
        with self._lock:
            self._check_planning_revision(data.expected_revision)
            truck = self._truck(data.truck_id)
            driver = next(
                (
                    driver
                    for driver in ACTORS
                    if driver.id == data.driver_id and driver.role == Role.DRIVER
                ),
                None,
            )
            if driver is None:
                raise HTTPException(422, "Selecciona un conductor de demostración")
            if truck.trip_id or not truck.order_codes:
                raise HTTPException(
                    409, "El camión debe tener carga guardada y ningún viaje asignado"
                )
            if any(
                trip.driver_id == driver.id and trip.status in ACTIVE_TRIP_STATUSES
                for trip in self._trips.values()
            ):
                raise HTTPException(409, "El conductor ya tiene un viaje asignado")
            orders = [self._orders[code] for code in truck.order_codes]
            if any(
                order.status != OrderStatus.READY
                or order.trip_id
                or not order.scheduled_departure_at
                for order in orders
            ):
                raise HTTPException(409, "Todos los pedidos deben estar listos y sin viaje")
            trip = TripState(
                id=str(uuid.uuid4()),
                truck_id=truck.id,
                truck_name=truck.name,
                driver_id=driver.id,
                driver_name=driver.name,
                capacity=truck.capacity,
                load_units=sum(load_units(order) for order in orders),
                order_codes=list(truck.order_codes),
                stops=[
                    TripStop(
                        position=index,
                        code=order.code,
                        address=order.address,
                        location=order.location,
                        load_units=load_units(order),
                        items=order.items,
                        contact_name=order.contact_name,
                        contact_email=order.contact_email,
                        contact_phone=order.contact_phone,
                        instructions=order.instructions,
                        order_revision=order.revision + 1,
                    ).model_copy(deep=True)
                    for index, order in enumerate(orders, start=1)
                ],
                created_at=datetime.now(UTC),
                planned_departure_at=min(order.scheduled_departure_at for order in orders),
            )
            self._event(trip, actor, "Viaje asignado")
            self._trips[trip.id] = trip
            truck.trip_id = trip.id
            for order in orders:
                order.trip_id = trip.id
                order.assigned_driver_name = driver.name
                self._record(order, actor, "Viaje asignado", f"{truck.name} · {driver.name}")
            self._planning_revision += 1
            return self._output(trip)

    def cancel_trip(self, trip_id: str, data: RevisionInput, actor: DemoActor) -> TripOutput:
        with self._lock:
            trip = self._trip(trip_id)
            if trip.revision != data.expected_revision or trip.status not in (
                "asignado",
                "carga_confirmada",
            ):
                raise HTTPException(409, "Solo se libera un viaje vigente antes de su salida")
            trip.status = "cancelado"
            trip.revision += 1
            self._event(trip, actor, "Viaje liberado antes de salir")
            self._truck(trip.truck_id).trip_id = None
            for code in trip.order_codes:
                order = self._orders[code]
                order.trip_id = None
                order.assigned_driver_name = None
                self._record(order, actor, "Viaje liberado antes de salir")
            self._planning_revision += 1
            return self._output(trip)

    def driver_trip(self, actor: DemoActor, trip_id: str | None = None) -> TripOutput | None:
        with self._lock:
            if trip_id:
                return self._output(self._trip(trip_id, actor))
            trip = next(
                (
                    trip
                    for trip in self._trips.values()
                    if trip.driver_id == actor.id and trip.status in ACTIVE_TRIP_STATUSES
                ),
                None,
            )
            return self._output(trip) if trip else None

    def driver_closed_trips(self, actor: DemoActor) -> list[TripOutput]:
        with self._lock:
            return [
                self._output(trip)
                for trip in reversed(list(self._trips.values()))
                if trip.driver_id == actor.id and trip.status in ("completado", "reprogramado")
            ]

    def driver_action(self, trip_id: str, data: DriverAction, actor: DemoActor) -> TripOutput:
        with self._lock:
            trip = self._trip(trip_id, actor)
            if trip.revision != data.expected_revision:
                raise HTTPException(409, "El viaje cambió. Actualiza antes de continuar")
            if data.action == "confirm_load":
                if trip.status != "asignado":
                    raise HTTPException(409, "La carga no permite esta confirmación")
                trip.status = "carga_confirmada"
                label = "Carga confirmada por conductor"
            elif data.action == "start_trip":
                if trip.status != "carga_confirmada":
                    raise HTTPException(409, "Confirma la carga antes de iniciar el viaje")
                trip.status = "en_camino"
                trip.actual_departure_at = datetime.now(UTC)
                for code in active_codes(trip):
                    self._orders[code].status = OrderStatus.IN_TRANSIT
                    self._orders[code].actual_departure_at = trip.actual_departure_at
                self._planning_revision += 1
                label = "Viaje iniciado"
            else:
                if trip.active_incident_id:
                    raise HTTPException(409, "Resuelve el incidente de ruta antes de avanzar")
                if trip.status != "en_camino" or trip.progress_percent == 100:
                    raise HTTPException(409, "El viaje no permite avanzar la simulación")
                trip.progress_percent += 25
                label = "Avance simulado del recorrido"
            trip.revision += 1
            self._event(trip, actor, label)
            for code in active_codes(trip):
                self._record(
                    self._orders[code],
                    actor,
                    label,
                    f"{trip.progress_percent}% del recorrido simulado"
                    if data.action == "advance"
                    else "",
                )
            return self._output(trip)

    def tracking(self, code: str, actor: DemoActor) -> CustomerTracking:
        with self._lock:
            order = self.get_for(actor.id, code)
            if order.status == OrderStatus.DELIVERED:
                return CustomerTracking(
                    code=order.code,
                    status="entregado",
                    revision=order.revision,
                    delivery_mode=order.delivery_mode,
                    partner_name=order.third_party.partner.name if order.third_party else None,
                    service_reference=order.third_party.reference if order.third_party else None,
                    truck_name=order.assigned_truck_name,
                    driver_name=order.assigned_driver_name,
                    actual_departure_at=order.actual_departure_at,
                    delivered_at=order.delivered_at,
                    destination=order.location,
                    estimated_delivery_at=order.estimated_delivery_at,
                )
            if order.third_party is not None:
                return CustomerTracking(
                    code=order.code,
                    status=order.third_party.status,
                    revision=order.revision,
                    delivery_mode="tercero",
                    partner_name=order.third_party.partner.name,
                    service_reference=order.third_party.reference,
                    progress_percent=order.third_party.progress_percent,
                    actual_departure_at=order.actual_departure_at,
                    destination=order.location,
                    estimated_delivery_at=order.estimated_delivery_at,
                )
            if not order.trip_id:
                return CustomerTracking(
                    code=order.code,
                    status="sin_viaje",
                    revision=order.revision,
                    destination=order.location,
                    estimated_delivery_at=order.estimated_delivery_at,
                    needs_reschedule=order.needs_reschedule,
                )
            trip = self._trip(order.trip_id)
            return CustomerTracking(
                code=order.code,
                status=trip.status,
                revision=order.revision,
                delivery_mode="flota_propia",
                truck_name=trip.truck_name,
                driver_name=trip.driver_name,
                actual_departure_at=trip.actual_departure_at,
                progress_percent=trip.progress_percent,
                position=simulated_position(trip),
                destination=order.location,
                route_complete=all(point is not None for point in route_points(trip)),
                incident_message=(
                    "Incidente de ruta en atención: avance pausado"
                    if trip.active_incident_id
                    else None
                ),
                estimated_delivery_at=order.estimated_delivery_at,
                needs_reschedule=order.needs_reschedule,
            )


def driver(local: LocalDemo, actor_id: Annotated[str, Header(alias="X-Demo-Actor")]) -> DemoActor:
    actor = next(
        (actor for actor in ACTORS if actor.id == actor_id and actor.role == Role.DRIVER), None
    )
    if actor is None:
        raise HTTPException(403, "Selecciona un conductor de demostración")
    return actor


Driver = Annotated[DemoActor, Depends(driver)]


@trip_router.get("/company/trips", response_model=DispatchSnapshot)
def dispatch(actor: Company, request: Request) -> DispatchSnapshot:
    return request.app.state.demo_orders.dispatch()


@trip_router.post("/company/trips", response_model=TripOutput, status_code=201)
def create_trip(data: TripInput, actor: Company, request: Request) -> TripOutput:
    return request.app.state.demo_orders.create_trip(data, actor)


@trip_router.post("/company/trips/{trip_id}/cancel", response_model=TripOutput)
def cancel_trip(trip_id: str, data: RevisionInput, actor: Company, request: Request) -> TripOutput:
    return request.app.state.demo_orders.cancel_trip(trip_id, data, actor)


@trip_router.get("/driver/trip", response_model=TripOutput | None)
def driver_trip(actor: Driver, request: Request) -> TripOutput | None:
    return request.app.state.demo_orders.driver_trip(actor)


@trip_router.get("/driver/trips/{trip_id}", response_model=TripOutput)
def driver_trip_detail(trip_id: str, actor: Driver, request: Request) -> TripOutput:
    return request.app.state.demo_orders.driver_trip(actor, trip_id)


@trip_router.get("/driver/trips", response_model=list[TripOutput])
def driver_closed_trips(actor: Driver, request: Request) -> list[TripOutput]:
    return request.app.state.demo_orders.driver_closed_trips(actor)


@trip_router.post("/driver/trips/{trip_id}/actions", response_model=TripOutput)
def driver_action(trip_id: str, data: DriverAction, actor: Driver, request: Request) -> TripOutput:
    return request.app.state.demo_orders.driver_action(trip_id, data, actor)


@trip_router.get("/orders/{code}/tracking", response_model=CustomerTracking)
def tracking(code: str, actor: Customer, request: Request) -> CustomerTracking:
    return request.app.state.demo_orders.tracking(code, actor)
