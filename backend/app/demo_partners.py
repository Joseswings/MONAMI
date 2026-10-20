"""Aliados ficticios: solicitud, aceptación y seguimiento manual, sin comunicaciones externas."""

import secrets
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.demo import (
    Company,
    DeliveryPartner,
    DemoActor,
    OrderEvent,
    OrderOutput,
    OrderStatus,
    RevisionInput,
    ScheduleInput,
    ThirdPartyService,
)
from app.demo_fleet import departure_day, load_units
from app.demo_incidents import DemoIncidentStore, Reason

partner_router = APIRouter(prefix="/api/v1/demo/company", tags=["aliados simulados"])
PARTNERS = (
    DeliveryPartner(
        id="aliado-1",
        name="PaqueteríaTest",
        contact_name="Coordinación de prueba",
        contact_email="servicios@paqueteriatest.test",
        instructions="Copiar contacto o solicitud para ensayar. Esta dirección es ficticia.",
    ),
    DeliveryPartner(
        id="aliado-2",
        name="EnvíosTest",
        contact_name="Despacho de prueba",
        contact_email="servicios@enviostest.test",
        instructions="Servicio simulado, sin conexión ni envío de mensajes al aliado.",
    ),
)


class ThirdPartyRequest(RevisionInput):
    partner_id: str = Field(min_length=1, max_length=80)
    reason: Reason


class ThirdPartyAction(RevisionInput):
    action: Literal["confirm", "dispatch", "advance", "cancel", "deliver"]
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_note(self):
        self.note = self.note.strip()
        if self.action == "cancel" and not self.note:
            raise ValueError("Indica por qué cancelas el servicio")
        return self


class ThirdPartyCandidate(BaseModel):
    order: OrderOutput
    fleet_assessment: str
    compatible_trucks: list[str]


class ThirdPartySnapshot(BaseModel):
    revision: int
    partners: list[DeliveryPartner]
    candidates: list[ThirdPartyCandidate]
    services: list[OrderOutput]


class DemoPartnerStore(DemoIncidentStore):
    def third_party_snapshot(self) -> ThirdPartySnapshot:
        with self._lock:
            candidates = []
            for order in reversed(list(self._orders.values())):
                if (
                    order.status != OrderStatus.READY
                    or order.assigned_truck_id
                    or order.trip_id
                    or order.third_party
                ):
                    continue
                compatible = [
                    truck.name
                    for truck in self._trucks.values()
                    if not truck.trip_id
                    and (
                        not truck.order_codes
                        or departure_day(self._orders[truck.order_codes[0]]) == departure_day(order)
                    )
                    and truck.capacity - sum(load_units(self._orders[c]) for c in truck.order_codes)
                    >= load_units(order)
                ]
                if load_units(order) > max(truck.capacity for truck in self._trucks.values()):
                    assessment = "El pedido supera la capacidad de cualquier camión simulado"
                elif not compatible:
                    assessment = "Sin camión compatible por reserva, día o capacidad disponible"
                else:
                    assessment = "Hay capacidad compatible; la empresa debe revisar la cobertura"
                candidates.append(
                    ThirdPartyCandidate(
                        order=order.model_copy(deep=True),
                        fleet_assessment=assessment,
                        compatible_trucks=compatible,
                    )
                )
            return ThirdPartySnapshot(
                revision=self._planning_revision,
                partners=[partner.model_copy(deep=True) for partner in PARTNERS],
                candidates=candidates,
                services=[
                    order.model_copy(deep=True)
                    for order in reversed(list(self._orders.values()))
                    if order.third_party is not None
                ],
            )

    @staticmethod
    def _service_event(service: ThirdPartyService, actor: DemoActor, label: str, note: str) -> None:
        service.history.append(
            OrderEvent(action=label, actor_name=actor.name, at=datetime.now(UTC), note=note)
        )

    def request_third_party(
        self, code: str, data: ThirdPartyRequest, actor: DemoActor
    ) -> OrderOutput:
        with self._lock:
            order = self._find(code)
            self._check_revision(order, data.expected_revision)
            partner = next((partner for partner in PARTNERS if partner.id == data.partner_id), None)
            if partner is None:
                raise HTTPException(404, "Aliado de prueba no encontrado")
            if (
                order.status != OrderStatus.READY
                or not order.scheduled_departure_at
                or order.assigned_truck_id
                or order.trip_id
                or order.third_party is not None
            ):
                raise HTTPException(409, "El pedido debe estar listo, con salida y sin transporte")
            service = ThirdPartyService(
                id=str(uuid.uuid4()),
                reference=f"TP-{secrets.token_hex(6).upper()}",
                partner=partner.model_copy(deep=True),
                reason=data.reason,
                requested_at=datetime.now(UTC),
            )
            self._service_event(service, actor, "Solicitud simulada de servicio", data.reason)
            order.third_party = service
            order.delivery_mode = "tercero"
            self._planning_revision += 1
            return self._record(
                order,
                actor,
                "Entrega por tercero: pendiente de aceptación",
                f"{partner.name}: {data.reason}",
            )

    def third_party_action(
        self, code: str, data: ThirdPartyAction, actor: DemoActor
    ) -> OrderOutput:
        with self._lock:
            order = self._find(code)
            self._check_revision(order, data.expected_revision)
            service = order.third_party
            if service is None:
                raise HTTPException(409, "El pedido no tiene un servicio por tercero activo")
            now = datetime.now(UTC)
            if data.action == "cancel":
                if service.status not in ("pendiente_aceptacion", "confirmado"):
                    raise HTTPException(409, "Solo se cancela el servicio antes del despacho")
                service.status, service.cancelled_at = "cancelado", now
                label = "Servicio por tercero cancelado"
            elif data.action == "confirm":
                if service.status != "pendiente_aceptacion" or order.status != OrderStatus.READY:
                    raise HTTPException(409, "El servicio no está pendiente de aceptación")
                service.status, service.confirmed_at = "confirmado", now
                label = "Aceptación simulada del aliado"
            elif data.action == "dispatch":
                if service.status != "confirmado" or order.status != OrderStatus.READY:
                    raise HTTPException(409, "Confirma el servicio antes de despachar")
                service.status, service.dispatched_at = "en_camino", now
                order.status, order.actual_departure_at = OrderStatus.IN_TRANSIT, now
                label = "Pedido despachado por tercero (simulado)"
            elif data.action == "deliver":
                if service.status != "en_camino" or order.status != OrderStatus.IN_TRANSIT:
                    raise HTTPException(409, "Despacha el servicio antes de confirmar la entrega")
                service.status, service.delivered_at = "entregado", now
                order.status, order.delivered_at = OrderStatus.DELIVERED, now
                order.delivered_by, order.delivery_note = actor.name, data.note
                label = "Entrega por tercero confirmada por empresa (simulada)"
            else:
                if (
                    service.status != "en_camino"
                    or order.status != OrderStatus.IN_TRANSIT
                    or service.progress_percent == 100
                ):
                    raise HTTPException(409, "El servicio no permite avanzar la simulación")
                service.progress_percent += 25
                label = "Avance simulado por tercero"
            detail = f"{service.partner.name} · {service.reference}"
            if data.action == "advance":
                detail += f" · {service.progress_percent}%"
            if data.note:
                detail += f" · {data.note}"
            self._service_event(service, actor, label, detail)
            if data.action == "cancel":
                order.third_party_history.append(service.model_copy(deep=True))
                order.third_party = None
                order.delivery_mode = None
            self._planning_revision += 1
            return self._record(order, actor, label, detail)

    def schedule(self, code: str, actor: DemoActor, data: ScheduleInput) -> OrderOutput:
        with self._lock:
            if self._find(code).third_party is not None:
                raise HTTPException(409, "Cancela el servicio por tercero antes de ajustar fechas")
            return super().schedule(code, actor, data)


@partner_router.get("/third-party", response_model=ThirdPartySnapshot)
def third_party_snapshot(actor: Company, request: Request) -> ThirdPartySnapshot:
    return request.app.state.demo_orders.third_party_snapshot()


@partner_router.post("/orders/{code}/third-party/request", response_model=OrderOutput)
def request_third_party(
    code: str, data: ThirdPartyRequest, actor: Company, request: Request
) -> OrderOutput:
    return request.app.state.demo_orders.request_third_party(code, data, actor)


@partner_router.post("/orders/{code}/third-party/actions", response_model=OrderOutput)
def third_party_action(
    code: str, data: ThirdPartyAction, actor: Company, request: Request
) -> OrderOutput:
    return request.app.state.demo_orders.third_party_action(code, data, actor)
