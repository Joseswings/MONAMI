"""Cierre explícito de entregas propias; la empresa simula las de terceros."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from app.demo import DemoActor, OrderStatus, RevisionInput
from app.demo_incidents import remaining_route
from app.demo_partners import DemoPartnerStore
from app.demo_trips import Driver, TripOutput, active_codes

delivery_router = APIRouter(prefix="/api/v1/demo/driver", tags=["entregas simuladas"])


class DeliveryInput(RevisionInput):
    expected_order_revision: int = Field(strict=True, ge=1)
    note: str = Field(default="", max_length=1000)


class DemoDeliveryStore(DemoPartnerStore):
    def deliver_order(
        self, trip_id: str, code: str, data: DeliveryInput, actor: DemoActor
    ) -> TripOutput:
        with self._lock:
            trip = self._trip(trip_id, actor)
            self._check_trip(trip, data.expected_revision)
            if code.upper() not in active_codes(trip):
                raise HTTPException(404, "El pedido no pertenece a este viaje activo")
            order = self._find(code)
            self._check_revision(order, data.expected_order_revision)
            if (
                order.status != OrderStatus.IN_TRANSIT
                or order.needs_reschedule
                or trip.active_incident_id
            ):
                raise HTTPException(
                    409, "Resuelve el problema o incidente antes de confirmar entrega"
                )
            points = remaining_route(trip)
            if order.location:
                for index in range(1, len(points)):
                    if points[index] == order.location:
                        points.pop(index)
                        break
            order.status, order.delivered_at = OrderStatus.DELIVERED, datetime.now(UTC)
            order.delivered_by, order.delivery_note = actor.name, data.note.strip()
            self._record(order, actor, "Entrega confirmada por conductor", order.delivery_note)
            trip.completed_order_codes.append(order.code)
            self._truck(trip.truck_id).order_codes.remove(order.code)
            trip.route_points = [point.model_copy(deep=True) if point else None for point in points]
            trip.route_start_percent = trip.progress_percent
            trip.revision += 1
            self._event(trip, actor, "Entrega confirmada: " + order.code)
            self._finish_if_resolved(trip, actor)
            self._planning_revision += 1
            return self._output(trip)


@delivery_router.post("/trips/{trip_id}/orders/{code}/deliver", response_model=TripOutput)
def deliver_order(
    trip_id: str, code: str, data: DeliveryInput, actor: Driver, request: Request
) -> TripOutput:
    return request.app.state.demo_orders.deliver_order(trip_id, code, data, actor)
