"""Incidentes y reintentos del MVP local. Las alternativas son geometría simulada."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, StringConstraints

from app.demo import (
    Company,
    DeliveryAttempt,
    DemoActor,
    Location,
    OrderOutput,
    OrderStatus,
    RevisionInput,
    ScheduleInput,
)
from app.demo_fleet import distance_km
from app.demo_trips import (
    DemoTripStore,
    Driver,
    RouteIncident,
    TripOutput,
    TripState,
    active_codes,
    route_points,
    simulated_position,
)
from app.models import Role

incident_router = APIRouter(prefix="/api/v1/demo", tags=["incidentes simulados"])
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class IncidentInput(RevisionInput):
    kind: Literal["bloqueo", "accidente"]
    reason: Reason


class ResolutionInput(RevisionInput):
    decision: Literal["alternativa", "continuar"]
    delay_minutes: int = Field(strict=True, ge=0, le=1440)
    resolution_note: Reason


class AlternativeOutput(BaseModel):
    revision: int
    incident_id: str
    points: list[Location]


class ProblemInput(RevisionInput):
    expected_order_revision: int = Field(strict=True, ge=1)
    reason: Reason


class RescheduleInput(ScheduleInput):
    expected_trip_revision: int = Field(strict=True, ge=1)
    resolution_note: Reason


def remaining_route(trip: TripState) -> list[Location | None]:
    position = simulated_position(trip)
    points = route_points(trip)
    if any(point is None for point in points):
        return [
            position,
            *(stop.location for stop in trip.stops if stop.code in active_codes(trip)),
        ]
    if trip.progress_percent == 100:
        return [position]
    lengths = [distance_km(a, b) for a, b in zip(points, points[1:], strict=False)]
    remaining = (
        sum(lengths)
        * (trip.progress_percent - trip.route_start_percent)
        / (100 - trip.route_start_percent)
    )
    for index, length in enumerate(lengths):
        if remaining < length:
            return [position, *points[index + 1 :]]
        remaining -= length
    return [position]


class DemoIncidentStore(DemoTripStore):
    @staticmethod
    def _check_trip(trip: TripState, revision: int) -> None:
        if trip.revision != revision or trip.status != "en_camino":
            raise HTTPException(409, "El viaje cambió o todavía no está en camino")

    @staticmethod
    def _open_incident(trip: TripState, incident_id: str) -> RouteIncident:
        incident = next((item for item in trip.incidents if item.id == incident_id), None)
        if incident is None:
            raise HTTPException(404, "Incidente no encontrado")
        if incident.id != trip.active_incident_id or incident.status != "abierto":
            raise HTTPException(409, "El incidente ya fue resuelto")
        return incident

    def report_incident(self, trip_id: str, data: IncidentInput, actor: DemoActor) -> TripOutput:
        with self._lock:
            trip = self._trip(trip_id, actor if actor.role == Role.DRIVER else None)
            self._check_trip(trip, data.expected_revision)
            if trip.active_incident_id or trip.progress_percent == 100:
                raise HTTPException(409, "No se puede abrir otro incidente en este punto del viaje")
            incident = RouteIncident(
                id=str(uuid.uuid4()),
                kind=data.kind,
                reason=data.reason,
                reported_by=actor.name,
                reported_at=datetime.now(UTC),
                progress_percent=trip.progress_percent,
                position=simulated_position(trip),
                route_before=route_points(trip),
            ).model_copy(deep=True)
            trip.incidents.append(incident)
            trip.active_incident_id = incident.id
            trip.revision += 1
            self._event(trip, actor, f"Incidente de ruta: {data.kind}")
            for code in active_codes(trip):
                self._record(self._orders[code], actor, "Incidente de ruta en atención", data.kind)
            return self._output(trip)

    def alternative(self, trip_id: str, incident_id: str, data: RevisionInput) -> AlternativeOutput:
        with self._lock:
            trip = self._trip(trip_id)
            self._check_trip(trip, data.expected_revision)
            self._open_incident(trip, incident_id)
            points = remaining_route(trip)
            if len(points) < 2 or any(point is None for point in points):
                raise HTTPException(
                    409, "Faltan coordenadas o un tramo pendiente para proponer la alternativa"
                )
            start, target = points[:2]
            longitude_delta = (target.longitude - start.longitude + 180) % 360 - 180
            detour = Location(
                latitude=max(-85, min(85, (start.latitude + target.latitude) / 2 + 0.006)),
                longitude=(start.longitude + longitude_delta / 2 - 0.006 + 180) % 360 - 180,
            )
            return AlternativeOutput(
                revision=trip.revision, incident_id=incident_id, points=[start, detour, *points[1:]]
            ).model_copy(deep=True)

    def resolve_incident(
        self, trip_id: str, incident_id: str, data: ResolutionInput, actor: DemoActor
    ) -> TripOutput:
        with self._lock:
            trip = self._trip(trip_id)
            self._check_trip(trip, data.expected_revision)
            incident = self._open_incident(trip, incident_id)
            points = (
                self.alternative(trip_id, incident_id, data).points
                if data.decision == "alternativa"
                else remaining_route(trip)
            )
            now = datetime.now(UTC)
            incident.status = "resuelto"
            incident.resolved_by, incident.resolved_at = actor.name, now
            incident.decision, incident.resolution_note = data.decision, data.resolution_note
            incident.delay_minutes = data.delay_minutes
            incident.alternative = (
                [point.model_copy(deep=True) for point in points]
                if data.decision == "alternativa"
                else None
            )
            trip.route_points = [point.model_copy(deep=True) if point else None for point in points]
            trip.route_start_percent = trip.progress_percent
            trip.active_incident_id = None
            trip.revision += 1
            self._event(
                trip,
                actor,
                "Alternativa simulada aprobada"
                if data.decision == "alternativa"
                else "Incidente resuelto: continuar recorrido",
            )
            for code in active_codes(trip):
                order = self._orders[code]
                order.estimated_delivery_at = max(
                    order.estimated_delivery_at or now, now
                ) + timedelta(minutes=data.delay_minutes)
                self._record(
                    order,
                    actor,
                    "Estimación de entrega actualizada",
                    f"Demora adicional simulada: {data.delay_minutes} minutos",
                    schedule=True,
                )
            return self._output(trip)

    def report_problem(
        self, trip_id: str, code: str, data: ProblemInput, actor: DemoActor
    ) -> TripOutput:
        with self._lock:
            trip = self._trip(trip_id, actor)
            self._check_trip(trip, data.expected_revision)
            if code.upper() not in active_codes(trip):
                raise HTTPException(404, "El pedido no pertenece a este viaje activo")
            order = self._find(code)
            self._check_revision(order, data.expected_order_revision)
            if order.needs_reschedule or order.status != OrderStatus.IN_TRANSIT:
                raise HTTPException(
                    409, "El pedido ya tiene un problema pendiente o no está en camino"
                )
            order.needs_reschedule = True
            order.delivery_attempts.append(
                DeliveryAttempt(
                    id=str(uuid.uuid4()),
                    trip_id=trip.id,
                    reported_at=datetime.now(UTC),
                    reported_by=actor.name,
                    reason=data.reason,
                    actual_departure_at=trip.actual_departure_at,
                )
            )
            self._record(order, actor, "Entrega con problema", data.reason)
            trip.revision += 1
            self._event(trip, actor, "Pedido con problema: requiere reprogramación")
            return self._output(trip)

    def reschedule(self, code: str, data: RescheduleInput, actor: DemoActor) -> OrderOutput:
        with self._lock:
            order = self._find(code)
            self._check_revision(order, data.expected_revision)
            if (
                not order.trip_id
                or not order.needs_reschedule
                or order.status != OrderStatus.IN_TRANSIT
            ):
                raise HTTPException(
                    409, "Solo se reprograman pedidos en camino con problema pendiente"
                )
            trip = self._trip(order.trip_id)
            self._check_trip(trip, data.expected_trip_revision)
            attempt = next(
                (
                    item
                    for item in reversed(order.delivery_attempts)
                    if item.trip_id == trip.id and item.status == "pendiente"
                ),
                None,
            )
            if attempt is None:
                raise HTTPException(409, "No hay un intento pendiente para este pedido")
            points = remaining_route(trip)
            if order.location:
                for index in range(1, len(points)):
                    if points[index] == order.location:
                        points.pop(index)
                        break
            now = datetime.now(UTC)
            attempt.status, attempt.resolved_at, attempt.resolved_by = (
                "reprogramado",
                now,
                actor.name,
            )
            attempt.resolution_note = data.resolution_note
            attempt.scheduled_departure_at = data.scheduled_departure_at.astimezone(UTC)
            attempt.estimated_delivery_at = (
                data.estimated_delivery_at.astimezone(UTC) if data.estimated_delivery_at else None
            )
            order.scheduled_departure_at, order.estimated_delivery_at = (
                attempt.scheduled_departure_at,
                attempt.estimated_delivery_at,
            )
            order.needs_reschedule = False
            order.status = OrderStatus.READY
            order.trip_id = order.assigned_truck_id = order.assigned_truck_name = (
                order.assigned_driver_name
            ) = None
            order.delivery_mode = None
            order.actual_departure_at = None
            trip.excluded_order_codes.append(order.code)
            self._truck(trip.truck_id).order_codes.remove(order.code)
            trip.route_points = [point.model_copy(deep=True) if point else None for point in points]
            trip.route_start_percent = trip.progress_percent
            trip.revision += 1
            self._record(order, actor, "Entrega reprogramada", data.resolution_note, schedule=True)
            self._event(trip, actor, "Pedido retirado para reprogramación")
            self._finish_if_resolved(trip, actor)
            self._planning_revision += 1
            return order.model_copy(deep=True)


@incident_router.post("/company/trips/{trip_id}/incidents", response_model=TripOutput)
def company_incident(
    trip_id: str, data: IncidentInput, actor: Company, request: Request
) -> TripOutput:
    return request.app.state.demo_orders.report_incident(trip_id, data, actor)


@incident_router.post("/driver/trips/{trip_id}/incidents", response_model=TripOutput)
def driver_incident(
    trip_id: str, data: IncidentInput, actor: Driver, request: Request
) -> TripOutput:
    return request.app.state.demo_orders.report_incident(trip_id, data, actor)


@incident_router.post(
    "/company/trips/{trip_id}/incidents/{incident_id}/alternative", response_model=AlternativeOutput
)
def alternative(
    trip_id: str, incident_id: str, data: RevisionInput, actor: Company, request: Request
) -> AlternativeOutput:
    return request.app.state.demo_orders.alternative(trip_id, incident_id, data)


@incident_router.post(
    "/company/trips/{trip_id}/incidents/{incident_id}/resolve", response_model=TripOutput
)
def resolve(
    trip_id: str, incident_id: str, data: ResolutionInput, actor: Company, request: Request
) -> TripOutput:
    return request.app.state.demo_orders.resolve_incident(trip_id, incident_id, data, actor)


@incident_router.post("/driver/trips/{trip_id}/orders/{code}/problem", response_model=TripOutput)
def problem(
    trip_id: str, code: str, data: ProblemInput, actor: Driver, request: Request
) -> TripOutput:
    return request.app.state.demo_orders.report_problem(trip_id, code, data, actor)


@incident_router.post("/company/orders/{code}/reschedule", response_model=OrderOutput)
def reschedule(code: str, data: RescheduleInput, actor: Company, request: Request) -> OrderOutput:
    return request.app.state.demo_orders.reschedule(code, data, actor)
