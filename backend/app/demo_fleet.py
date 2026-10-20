"""Planificación local: capacidad ficticia, cercanía geométrica y asignación explícita."""

from datetime import UTC, date, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.demo import (
    Company,
    CompanyAction,
    DemoActor,
    DemoOrderStore,
    Location,
    OrderOutput,
    OrderStatus,
    RevisionInput,
    ScheduleInput,
)

fleet_router = APIRouter(prefix="/api/v1/demo/company", tags=["planificación local"])
OrderCode = Annotated[
    str, StringConstraints(to_upper=True, pattern=r"^[Mm][Oo][Nn]-[a-fA-F0-9]{8}$")
]
DEPOT = Location(latitude=14.6349, longitude=-90.5069)


def departure_day(order: OrderOutput) -> date | None:
    if order.scheduled_departure_at is None:
        return None
    # Día de salida en Guatemala, UTC−6, también usado por el formulario de fechas.
    return (order.scheduled_departure_at.astimezone(UTC) - timedelta(hours=6)).date()


def load_units(order: OrderOutput) -> int:
    return sum(item.quantity for item in order.items)


def distance_km(start: Location, end: Location) -> float:
    """Distancia de gran círculo; no estima kilómetros por carretera ni duración."""
    lat1, lat2 = radians(start.latitude), radians(end.latitude)
    delta_lat = lat2 - lat1
    delta_lon = radians(end.longitude - start.longitude)
    value = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 6371 * 2 * asin(sqrt(min(1.0, max(0.0, value))))


class TruckPlan(BaseModel):
    id: str
    name: str
    capacity: int
    order_codes: list[str] = Field(default_factory=list)
    trip_id: str | None = None


class PlannedStop(BaseModel):
    position: int
    code: str
    address: str
    location: Location | None
    load_units: int


class TruckOutput(TruckPlan):
    used_capacity: int
    remaining_capacity: int
    departure_date: date | None
    availability: Literal["disponible", "reservado", "completo", "viaje_asignado", "en_viaje"]
    stops: list[PlannedStop]
    route_complete: bool
    straight_line_km: float | None


class FleetSnapshot(BaseModel):
    revision: int
    depot: Location = DEPOT
    depot_name: str = "Bodega de prueba · Guatemala"
    capacity_unit: str = "Una unidad solicitada equivale a una unidad de carga simulada"
    trucks: list[TruckOutput]
    ready_orders: list[OrderOutput]


class SuggestionInput(RevisionInput):
    departure_date: date


class AssignmentInput(RevisionInput):
    departure_date: date | None = None
    order_codes: list[OrderCode] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_selection(self):
        if len(self.order_codes) != len(set(self.order_codes)):
            raise ValueError("No se puede repetir un pedido")
        if bool(self.order_codes) != bool(self.departure_date):
            raise ValueError("La fecha corresponde a un plan con pedidos")
        return self


class ExcludedOrder(BaseModel):
    code: str
    reason: str


class FleetSuggestion(BaseModel):
    revision: int
    truck_id: str
    departure_date: date
    order_codes: list[str]
    excluded: list[ExcludedOrder]


class DemoPlanningStore(DemoOrderStore):
    """Amplía el almacén simulado usando el mismo bloqueo para pedidos y camiones."""

    def __init__(self) -> None:
        super().__init__()
        self._planning_revision = 1
        self._trucks = {
            f"camion-{index}": TruckPlan(
                id=f"camion-{index}", name=f"Camión de prueba {index}", capacity=capacity
            )
            for index, capacity in enumerate((20, 40, 60), start=1)
        }

    def _truck(self, truck_id: str) -> TruckPlan:
        truck = self._trucks.get(truck_id)
        if truck is None:
            raise HTTPException(404, "Camión no encontrado")
        return truck

    def _check_planning_revision(self, revision: int) -> None:
        if self._planning_revision != revision:
            raise HTTPException(409, "La planificación cambió. Actualiza antes de guardar")

    def _truck_output(self, truck: TruckPlan) -> TruckOutput:
        orders = [self._orders[code] for code in truck.order_codes]
        used = sum(load_units(order) for order in orders)
        complete = all(order.location is not None for order in orders)
        point, distance = DEPOT, 0.0
        for order in orders:
            if order.location:
                distance += distance_km(point, order.location)
                point = order.location
        return TruckOutput(
            **truck.model_dump(),
            used_capacity=used,
            remaining_capacity=truck.capacity - used,
            departure_date=departure_day(orders[0]) if orders else None,
            availability="en_viaje"
            if any(order.status == OrderStatus.IN_TRANSIT for order in orders)
            else "viaje_asignado"
            if truck.trip_id
            else "completo"
            if used == truck.capacity
            else "reservado"
            if orders
            else "disponible",
            route_complete=complete,
            straight_line_km=round(distance, 2) if complete else None,
            stops=[
                PlannedStop(
                    position=index,
                    code=order.code,
                    address=order.address,
                    location=order.location.model_copy(deep=True) if order.location else None,
                    load_units=load_units(order),
                )
                for index, order in enumerate(orders, start=1)
            ],
        )

    def planning(self) -> FleetSnapshot:
        with self._lock:
            return FleetSnapshot(
                revision=self._planning_revision,
                trucks=[self._truck_output(truck) for truck in self._trucks.values()],
                ready_orders=[
                    order.model_copy(deep=True)
                    for order in reversed(list(self._orders.values()))
                    if order.status == OrderStatus.READY and order.third_party is None
                ],
            )

    def act(self, code: str, actor: DemoActor, data: CompanyAction) -> OrderOutput:
        with self._lock:
            order = super().act(code, actor, data)
            if data.action == "mark_ready":
                self._planning_revision += 1
            return order

    def schedule(self, code: str, actor: DemoActor, data: ScheduleInput) -> OrderOutput:
        with self._lock:
            current = self._find(code)
            if current.trip_id:
                raise HTTPException(
                    409,
                    "Libera el viaje asignado antes de ajustar las fechas del pedido",
                )
            day = (data.scheduled_departure_at.astimezone(UTC) - timedelta(hours=6)).date()
            if current.assigned_truck_id and day != departure_day(current):
                raise HTTPException(
                    409, "Retira el pedido del camión antes de cambiar el día de salida"
                )
            order = super().schedule(code, actor, data)
            if order.status == OrderStatus.READY:
                self._planning_revision += 1
            return order

    def suggest(self, truck_id: str, data: SuggestionInput) -> FleetSuggestion:
        with self._lock:
            self._check_planning_revision(data.expected_revision)
            truck = self._truck(truck_id)
            if truck.trip_id:
                raise HTTPException(
                    409, "El camión tiene un viaje asignado y su carga está bloqueada"
                )
            existing = [self._orders[code] for code in truck.order_codes]
            if existing and departure_day(existing[0]) != data.departure_date:
                raise HTTPException(409, "El camión ya está reservado para otro día")
            selection = list(truck.order_codes)
            remaining = truck.capacity - sum(load_units(order) for order in existing)
            point = next((order.location for order in reversed(existing) if order.location), DEPOT)
            pool, excluded = [], []
            for order in self._orders.values():
                if (
                    order.status != OrderStatus.READY
                    or order.third_party is not None
                    or order.assigned_truck_id
                    or departure_day(order) != data.departure_date
                ):
                    continue
                if order.location is None:
                    excluded.append(
                        ExcludedOrder(
                            code=order.code,
                            reason="Sin punto en el mapa; puedes añadirlo manualmente",
                        )
                    )
                else:
                    pool.append(order)
            while pool:
                pool.sort(key=lambda order: (distance_km(point, order.location), order.code))
                order = pool.pop(0)
                if load_units(order) > remaining or len(selection) >= 100:
                    excluded.append(
                        ExcludedOrder(
                            code=order.code,
                            reason="Capacidad insuficiente o límite de 100 paradas alcanzado",
                        )
                    )
                    continue
                selection.append(order.code)
                remaining -= load_units(order)
                point = order.location
            return FleetSuggestion(
                revision=self._planning_revision,
                truck_id=truck_id,
                departure_date=data.departure_date,
                order_codes=selection,
                excluded=excluded,
            )

    def assign(self, truck_id: str, actor: DemoActor, data: AssignmentInput) -> FleetSnapshot:
        with self._lock:
            self._check_planning_revision(data.expected_revision)
            truck = self._truck(truck_id)
            if truck.trip_id:
                raise HTTPException(
                    409, "El camión tiene un viaje asignado y su carga está bloqueada"
                )
            orders = [self._find(code) for code in data.order_codes]
            if (
                truck.order_codes
                and orders
                and departure_day(self._orders[truck.order_codes[0]]) != data.departure_date
            ):
                raise HTTPException(409, "Libera el camión antes de reservarlo para otro día")
            for order in orders:
                if order.third_party is not None:
                    raise HTTPException(
                        409, "Cancela el servicio por tercero antes de asignar flota"
                    )
                if order.status != OrderStatus.READY:
                    raise HTTPException(409, "Solo se asignan pedidos listos para salir")
                if order.assigned_truck_id not in (None, truck_id):
                    raise HTTPException(409, "Uno de los pedidos pertenece a otro camión")
                if departure_day(order) != data.departure_date:
                    raise HTTPException(409, "Todos los pedidos deben compartir el día de salida")
            if sum(load_units(order) for order in orders) > truck.capacity:
                raise HTTPException(409, "La carga supera la capacidad simulada del camión")
            if data.order_codes == truck.order_codes:
                return self.planning()
            previous = list(truck.order_codes)
            # Se valida toda la propuesta antes de modificar pedidos o reservar capacidad.
            for code in previous:
                if code not in data.order_codes:
                    order = self._orders[code]
                    order.assigned_truck_id = None
                    order.assigned_truck_name = None
                    order.delivery_mode = None
                    self._record(order, actor, "Pedido retirado del camión", truck.name)
            for index, order in enumerate(orders):
                added = order.code not in previous
                moved = not added and previous.index(order.code) != index
                order.assigned_truck_id = truck.id
                order.assigned_truck_name = truck.name
                order.delivery_mode = "flota_propia"
                if added or moved:
                    self._record(
                        order,
                        actor,
                        "Asignación de camión" if added else "Orden de parada ajustado",
                        f"{truck.name} · Parada {index + 1}",
                    )
            truck.order_codes = list(data.order_codes)
            self._planning_revision += 1
            return self.planning()


@fleet_router.get("/planning", response_model=FleetSnapshot)
def planning(actor: Company, request: Request) -> FleetSnapshot:
    return request.app.state.demo_orders.planning()


@fleet_router.post("/trucks/{truck_id}/suggestion", response_model=FleetSuggestion)
def suggest(
    truck_id: str, data: SuggestionInput, actor: Company, request: Request
) -> FleetSuggestion:
    return request.app.state.demo_orders.suggest(truck_id, data)


@fleet_router.post("/trucks/{truck_id}/assignment", response_model=FleetSnapshot)
def assign(truck_id: str, data: AssignmentInput, actor: Company, request: Request) -> FleetSnapshot:
    return request.app.state.demo_orders.assign(truck_id, actor, data)
