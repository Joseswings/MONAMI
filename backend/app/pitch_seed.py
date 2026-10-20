"""Carga explícita e idempotente del escenario ficticio. Nunca se ejecuta al arrancar."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.database import build_engine
from app.demo import ACTORS, CompanyAction, OrderInput, ScheduleInput
from app.demo_deliveries import DemoDeliveryStore
from app.demo_fleet import AssignmentInput, departure_day
from app.demo_partners import ThirdPartyAction, ThirdPartyRequest
from app.demo_trips import DriverAction, TripInput
from app.models import PitchScenario
from app.pitch_state import check_schema, dump_store


def prepared_scenario(now: datetime | None = None) -> DemoDeliveryStore:
    now = now or datetime.now(UTC)
    departure = (now + timedelta(days=2)).replace(hour=15, minute=0, second=0, microsecond=0)
    store, company, driver = DemoDeliveryStore(), ACTORS[2], ACTORS[3]

    def order(index, customer=0, quantity=3, stage="ready"):
        result, _ = store.create(
            ACTORS[customer],
            OrderInput(
                contact_name=ACTORS[customer].name,
                contact_email=ACTORS[customer].email,
                contact_phone="55550000",
                address=f"Dirección ficticia {index}, Guatemala",
                instructions="Datos ficticios para presentar Monami. No realizar entregas reales.",
                items=[{"product": f"Paquete de prueba {index}", "quantity": quantity}],
                location={"latitude": 14.635 + index * 0.008, "longitude": -90.507 - index * 0.009},
            ),
            f"pitch-prepared-order-{index}",
        )
        if stage == "received":
            return result
        for action in ("confirm", "start_preparation"):
            result = store.act(
                result.code,
                company,
                CompanyAction(expected_revision=result.revision, action=action),
            )
        result = store.schedule(
            result.code,
            company,
            ScheduleInput(
                expected_revision=result.revision,
                scheduled_departure_at=departure,
                estimated_delivery_at=departure + timedelta(hours=4),
            ),
        )
        if stage == "preparing":
            return result
        return store.act(
            result.code,
            company,
            CompanyAction(expected_revision=result.revision, action="mark_ready"),
        )

    first, second = order(1), order(2, customer=1)
    store.assign(
        "camion-1",
        company,
        AssignmentInput(
            expected_revision=store.planning().revision,
            departure_date=departure_day(first),
            order_codes=[first.code, second.code],
        ),
    )
    trip = store.create_trip(
        TripInput(
            expected_revision=store.dispatch().revision, truck_id="camion-1", driver_id=driver.id
        ),
        company,
    )
    for action in ("confirm_load", "start_trip", "advance"):
        trip = store.driver_action(
            trip.id, DriverAction(expected_revision=trip.revision, action=action), driver
        )
    order(3, quantity=61)
    order(4, customer=1, stage="received")
    order(5, stage="preparing")
    external = order(6, customer=1)
    external = store.request_third_party(
        external.code,
        ThirdPartyRequest(
            expected_revision=external.revision,
            partner_id="aliado-1",
            reason="Cobertura externa de prueba",
        ),
        company,
    )
    for action in ("confirm", "dispatch", "deliver"):
        external = store.third_party_action(
            external.code,
            ThirdPartyAction(
                expected_revision=external.revision,
                action=action,
                note="Ejemplo ficticio preparado para el pitch",
            ),
            company,
        )
    return store


def initialize_scenario(engine: Engine, scenario_id: str) -> bool:
    payload = dump_store(prepared_scenario())
    with engine.begin() as connection:
        check_schema(connection)
        result = connection.execute(
            insert(PitchScenario)
            .values(
                id=scenario_id,
                generation=uuid.uuid4(),
                payload=payload,
                updated_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=[PitchScenario.id])
        )
        return result.rowcount == 1


def main() -> None:
    settings = Settings()
    if not settings.pitch_mode or settings.database_url is None:
        raise SystemExit("Configurar DEMO_MODE=false, PITCH_MODE=true y las variables de pitch")
    engine = build_engine(settings.database_url)
    try:
        created = initialize_scenario(engine, settings.pitch_scenario_id)
    except SQLAlchemyError:
        raise SystemExit(
            "No se pudo cargar el escenario; revisar conexión, migración y permisos"
        ) from None
    finally:
        engine.dispose()
    print(
        "Escenario de pitch creado"
        if created
        else "El escenario ya existe; no se reemplazaron sus datos"
    )


if __name__ == "__main__":
    main()
