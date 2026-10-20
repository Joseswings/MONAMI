"""Simulación local de pedidos. No autentica usuarios ni persiste datos."""

import secrets
import threading
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from ipaddress import ip_address
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models import Role

demo_router = APIRouter(tags=["demo local"])
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class DemoActor(BaseModel):
    id: str
    name: str
    email: str
    role: Role


ACTORS = (
    DemoActor(
        id="cliente-1", name="Cliente de prueba", email="cliente@empresatest.test", role=Role.CLIENT
    ),
    DemoActor(
        id="cliente-2", name="Segundo cliente", email="cliente2@empresatest.test", role=Role.CLIENT
    ),
    DemoActor(
        id="empresa", name="EmpresaTest", email="empresa@empresatest.test", role=Role.COMPANY
    ),
    DemoActor(
        id="conductor",
        name="Conductor de prueba",
        email="conductor@empresatest.test",
        role=Role.DRIVER,
    ),
    DemoActor(
        id="conductor-2",
        name="Segundo conductor",
        email="conductor2@empresatest.test",
        role=Role.DRIVER,
    ),
)


class DemoContext(BaseModel):
    mode: Literal["demo"] = "demo"
    company: str = "EmpresaTest"
    storage: Literal["memory", "postgresql"] = "memory"
    scenario_generation: str | None = None
    scenario_name: str | None = None
    actors: tuple[DemoActor, ...] = ACTORS


class OrderStatus(StrEnum):
    RECEIVED = "recibido"
    CONFIRMED = "confirmado"
    PREPARING = "preparando"
    READY = "listo_para_salir"
    IN_TRANSIT = "en_camino"
    DELIVERED = "entregado"


class OrderItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product: ShortText
    quantity: int = Field(strict=True, ge=1, le=100000)


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class OrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_name: ShortText
    contact_email: str = Field(max_length=254)
    contact_phone: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=5, max_length=40)
    ]
    items: list[OrderItem] = Field(min_length=1, max_length=20)
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]
    location: Location | None = None
    instructions: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""

    @field_validator("contact_email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        local, separator, domain = value.partition("@")
        if (
            not local
            or not separator
            or "@" in domain
            or "." not in domain
            or any(c.isspace() for c in value)
        ):
            raise ValueError("Correo de contacto no válido")
        return value


class OrderEvent(BaseModel):
    action: str
    actor_name: str
    at: datetime
    note: str = ""
    scheduled_departure_at: datetime | None = None
    estimated_delivery_at: datetime | None = None


class DeliveryAttempt(BaseModel):
    id: str
    trip_id: str
    reported_at: datetime
    reported_by: str
    reason: str
    actual_departure_at: datetime | None = None
    status: Literal["pendiente", "reprogramado"] = "pendiente"
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_note: str = ""
    scheduled_departure_at: datetime | None = None
    estimated_delivery_at: datetime | None = None


class DeliveryPartner(BaseModel):
    id: str
    name: str
    contact_name: str
    contact_email: str
    instructions: str


class ThirdPartyService(BaseModel):
    id: str
    reference: str
    partner: DeliveryPartner
    reason: str
    status: Literal["pendiente_aceptacion", "confirmado", "en_camino", "cancelado", "entregado"] = (
        "pendiente_aceptacion"
    )
    requested_at: datetime
    confirmed_at: datetime | None = None
    dispatched_at: datetime | None = None
    cancelled_at: datetime | None = None
    delivered_at: datetime | None = None
    progress_percent: int = 0
    history: list[OrderEvent] = Field(default_factory=list)


class OrderOutput(OrderInput):
    id: uuid.UUID
    code: str
    customer_id: str
    status: OrderStatus = OrderStatus.RECEIVED
    created_at: datetime
    scheduled_departure_at: datetime | None = None
    estimated_delivery_at: datetime | None = None
    delivered_at: datetime | None = None
    delivered_by: str | None = None
    delivery_note: str = ""
    delivery_mode: Literal["flota_propia", "tercero"] | None = None
    assigned_truck_id: str | None = None
    assigned_truck_name: str | None = None
    trip_id: str | None = None
    assigned_driver_name: str | None = None
    actual_departure_at: datetime | None = None
    needs_reschedule: bool = False
    delivery_attempts: list[DeliveryAttempt] = Field(default_factory=list)
    third_party: ThirdPartyService | None = None
    third_party_history: list[ThirdPartyService] = Field(default_factory=list)
    revision: int = 1
    correction_status: Literal["none", "requested", "resubmitted", "resolved"] = "none"
    correction_note: str = ""
    history: list[OrderEvent] = Field(default_factory=list)


class RevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(strict=True, ge=1)


class CompanyAction(RevisionInput):
    action: Literal["confirm", "request_correction", "start_preparation", "mark_ready"]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""

    @model_validator(mode="after")
    def validate_note(self):
        if self.action == "request_correction" and not self.note:
            raise ValueError("Indica qué debe corregir el cliente")
        if self.action != "request_correction" and self.note:
            raise ValueError("El motivo corresponde a una solicitud de corrección")
        return self


class ScheduleInput(RevisionInput):
    scheduled_departure_at: AwareDatetime
    estimated_delivery_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.scheduled_departure_at <= datetime.now(UTC):
            raise ValueError("La salida debe ser futura")
        if self.estimated_delivery_at and self.estimated_delivery_at < self.scheduled_departure_at:
            raise ValueError("La entrega no puede ser anterior a la salida")
        return self


class CorrectionInput(RevisionInput):
    order: OrderInput


class DemoOrderStore:
    def __init__(self) -> None:
        self._orders: dict[str, OrderOutput] = {}
        self._requests: dict[tuple[str, str], tuple[str, str]] = {}
        self._lock = threading.RLock()

    def create(self, actor: DemoActor, data: OrderInput, key: str) -> tuple[OrderOutput, bool]:
        fingerprint = data.model_dump_json()
        request_id = actor.id, key
        with self._lock:
            if request_id in self._requests:
                previous, code = self._requests[request_id]
                if previous != fingerprint:
                    raise HTTPException(409, "El identificador de envío ya se usó con otros datos")
                return self._orders[code].model_copy(deep=True), False
            code = f"MON-{secrets.token_hex(4).upper()}"
            while code in self._orders:
                code = f"MON-{secrets.token_hex(4).upper()}"
            order = OrderOutput(
                **data.model_dump(),
                id=uuid.uuid4(),
                code=code,
                customer_id=actor.id,
                created_at=datetime.now(UTC),
                history=[
                    OrderEvent(
                        action="Pedido recibido", actor_name=actor.name, at=datetime.now(UTC)
                    )
                ],
            )
            self._orders[code] = order
            self._requests[request_id] = fingerprint, code
            return order.model_copy(deep=True), True

    def list_for(self, actor_id: str) -> list[OrderOutput]:
        with self._lock:
            return [
                o.model_copy(deep=True)
                for o in reversed(list(self._orders.values()))
                if o.customer_id == actor_id
            ]

    def get_for(self, actor_id: str, code: str) -> OrderOutput:
        with self._lock:
            order = self._orders.get(code.upper())
            if order is None or order.customer_id != actor_id:
                raise HTTPException(404, "Pedido no encontrado para este cliente")
            return order.model_copy(deep=True)

    def list_company(self) -> list[OrderOutput]:
        # La simulación contiene una única organización: EmpresaTest.
        with self._lock:
            return [o.model_copy(deep=True) for o in reversed(list(self._orders.values()))]

    def get_company(self, code: str) -> OrderOutput:
        with self._lock:
            return self._find(code).model_copy(deep=True)

    def _find(self, code: str) -> OrderOutput:
        order = self._orders.get(code.upper())
        if order is None:
            raise HTTPException(404, "Pedido no encontrado")
        return order

    @staticmethod
    def _check_revision(order: OrderOutput, revision: int) -> None:
        if order.revision != revision:
            raise HTTPException(409, "El pedido cambió. Actualiza antes de continuar")

    @staticmethod
    def _record(
        order: OrderOutput, actor: DemoActor, action: str, note: str = "", schedule: bool = False
    ) -> OrderOutput:
        order.revision += 1
        order.history.append(
            OrderEvent(
                action=action,
                actor_name=actor.name,
                at=datetime.now(UTC),
                note=note,
                scheduled_departure_at=order.scheduled_departure_at if schedule else None,
                estimated_delivery_at=order.estimated_delivery_at if schedule else None,
            )
        )
        return order.model_copy(deep=True)

    def act(self, code: str, actor: DemoActor, data: CompanyAction) -> OrderOutput:
        with self._lock:
            order = self._find(code)
            self._check_revision(order, data.expected_revision)
            if data.action == "request_correction":
                if order.status != OrderStatus.RECEIVED or order.correction_status == "requested":
                    raise HTTPException(409, "Solo se solicitan correcciones antes de confirmar")
                order.correction_status = "requested"
                order.correction_note = data.note
                return self._record(order, actor, "Corrección solicitada", data.note)
            allowed = {
                "confirm": (OrderStatus.RECEIVED, OrderStatus.CONFIRMED, "Pedido confirmado"),
                "start_preparation": (
                    OrderStatus.CONFIRMED,
                    OrderStatus.PREPARING,
                    "Preparación iniciada",
                ),
                "mark_ready": (OrderStatus.PREPARING, OrderStatus.READY, "Pedido listo para salir"),
            }
            previous, next_status, label = allowed[data.action]
            if order.status != previous or order.correction_status == "requested":
                raise HTTPException(409, "El pedido no permite esta transición")
            if data.action == "mark_ready" and order.scheduled_departure_at is None:
                raise HTTPException(409, "Programa la salida antes de marcar el pedido como listo")
            order.status = next_status
            if data.action == "confirm" and order.correction_status == "resubmitted":
                order.correction_status = "resolved"
            return self._record(order, actor, label)

    def schedule(self, code: str, actor: DemoActor, data: ScheduleInput) -> OrderOutput:
        with self._lock:
            order = self._find(code)
            self._check_revision(order, data.expected_revision)
            if order.status not in (
                OrderStatus.CONFIRMED,
                OrderStatus.PREPARING,
                OrderStatus.READY,
            ):
                raise HTTPException(409, "Confirma el pedido antes de programar sus fechas")
            order.scheduled_departure_at = data.scheduled_departure_at.astimezone(UTC)
            order.estimated_delivery_at = (
                data.estimated_delivery_at.astimezone(UTC) if data.estimated_delivery_at else None
            )
            return self._record(order, actor, "Fechas programadas", schedule=True)

    def correct(self, code: str, actor: DemoActor, data: CorrectionInput) -> OrderOutput:
        with self._lock:
            order = self._find(code)
            if order.customer_id != actor.id:
                raise HTTPException(404, "Pedido no encontrado para este cliente")
            self._check_revision(order, data.expected_revision)
            if order.status != OrderStatus.RECEIVED or order.correction_status != "requested":
                raise HTTPException(409, "No hay una corrección pendiente para este pedido")
            for field in OrderInput.model_fields:
                # Reconstruir los modelos anidados, evitando asignar diccionarios sin validar.
                setattr(order, field, getattr(data.order, field))
            order.items = [item.model_copy(deep=True) for item in data.order.items]
            order.location = (
                data.order.location.model_copy(deep=True) if data.order.location else None
            )
            order.correction_status = "resubmitted"
            return self._record(order, actor, "Corrección enviada por cliente")


def local_demo(request: Request) -> None:
    if request.app.state.settings.pitch_mode:
        from app.pitch_access import require_pitch_session

        require_pitch_session(request)
        return
    try:
        local = request.client is not None and ip_address(request.client.host).is_loopback
    except ValueError:
        local = False
    if not local:
        raise HTTPException(403, "El modo simulado solo está disponible localmente")


LocalDemo = Annotated[None, Depends(local_demo)]


def customer(
    local: LocalDemo,
    actor_id: Annotated[str, Header(alias="X-Demo-Actor")],
) -> DemoActor:
    actor = next((a for a in ACTORS if a.id == actor_id), None)
    if actor is None or actor.role != Role.CLIENT:
        raise HTTPException(403, "Selecciona un cliente de demostración")
    return actor


Customer = Annotated[DemoActor, Depends(customer)]


def company(
    local: LocalDemo,
    actor_id: Annotated[str, Header(alias="X-Demo-Actor")],
) -> DemoActor:
    actor = next((a for a in ACTORS if a.id == actor_id), None)
    if actor is None or actor.role != Role.COMPANY:
        raise HTTPException(403, "Selecciona la empresa de demostración")
    return actor


Company = Annotated[DemoActor, Depends(company)]


@demo_router.get("/health/ready")
def demo_ready(request: Request) -> dict[str, str]:
    if request.app.state.settings.pitch_mode:
        request.app.state.demo_orders.metadata()
        return {"status": "pitch", "storage": "postgresql"}
    local_demo(request)
    return {"status": "demo", "storage": "memory"}


@demo_router.get("/api/v1/demo/context", response_model=DemoContext)
def context(local: LocalDemo, request: Request) -> DemoContext:
    if request.app.state.settings.pitch_mode:
        return DemoContext(storage="postgresql", **request.app.state.demo_orders.metadata())
    return DemoContext()


@demo_router.post("/api/v1/demo/orders", response_model=OrderOutput, status_code=201)
def create_order(
    data: OrderInput,
    actor: Customer,
    request: Request,
    response: Response,
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)],
) -> OrderOutput:
    order, created = request.app.state.demo_orders.create(actor, data, key)
    if not created:
        response.status_code = 200
    return order


@demo_router.get("/api/v1/demo/orders", response_model=list[OrderOutput])
def list_orders(actor: Customer, request: Request) -> list[OrderOutput]:
    return request.app.state.demo_orders.list_for(actor.id)


@demo_router.get("/api/v1/demo/orders/{code}", response_model=OrderOutput)
def get_order(code: str, actor: Customer, request: Request) -> OrderOutput:
    return request.app.state.demo_orders.get_for(actor.id, code)


@demo_router.post("/api/v1/demo/orders/{code}/correction", response_model=OrderOutput)
def correct_order(
    code: str, data: CorrectionInput, actor: Customer, request: Request
) -> OrderOutput:
    return request.app.state.demo_orders.correct(code, actor, data)


@demo_router.get("/api/v1/demo/company/orders", response_model=list[OrderOutput])
def company_orders(actor: Company, request: Request) -> list[OrderOutput]:
    return request.app.state.demo_orders.list_company()


@demo_router.get("/api/v1/demo/company/orders/{code}", response_model=OrderOutput)
def company_order(code: str, actor: Company, request: Request) -> OrderOutput:
    return request.app.state.demo_orders.get_company(code)


@demo_router.post("/api/v1/demo/company/orders/{code}/actions", response_model=OrderOutput)
def company_action(code: str, data: CompanyAction, actor: Company, request: Request) -> OrderOutput:
    return request.app.state.demo_orders.act(code, actor, data)


@demo_router.post("/api/v1/demo/company/orders/{code}/schedule", response_model=OrderOutput)
def schedule_order(code: str, data: ScheduleInput, actor: Company, request: Request) -> OrderOutput:
    return request.app.state.demo_orders.schedule(code, actor, data)
