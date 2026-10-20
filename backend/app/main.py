from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api import COMMON_ERRORS, database_health_router, router
from app.config import Settings
from app.database import build_engine
from app.demo import demo_router
from app.demo_deliveries import DemoDeliveryStore, delivery_router
from app.demo_fleet import fleet_router
from app.demo_incidents import incident_router
from app.demo_partners import partner_router
from app.demo_trips import trip_router
from app.pitch_access import pitch_router
from app.pitch_state import PersistentDemoStore, request_generation


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = (
            build_engine(configuration.database_url)
            if configuration.database_url and not configuration.demo_mode
            else None
        )
        if configuration.demo_mode:
            app.state.demo_orders = DemoDeliveryStore()
        elif configuration.pitch_mode:
            app.state.demo_orders = PersistentDemoStore(
                app.state.engine, configuration.pitch_scenario_id
            )
        try:
            yield
        finally:
            if app.state.engine is not None:
                app.state.engine.dispose()

    app = FastAPI(title="Monami API", version="0.1.0", lifespan=lifespan)
    app.state.settings = configuration
    app.state.engine = None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Demo-Actor",
            "Idempotency-Key",
            "X-Pitch-Generation",
        ],
    )

    @app.middleware("http")
    async def prevent_sensitive_caching(request: Request, call_next):
        generation_token = request_generation.set(request.headers.get("X-Pitch-Generation"))
        try:
            response = await call_next(request)
        finally:
            request_generation.reset(generation_token)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_unavailable(request: Request, exc: SQLAlchemyError):
        # No registrar el texto de excepciones del driver: puede contener datos sensibles.
        return JSONResponse(status_code=503, content={"detail": "Servicio de datos no disponible"})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Evita devolver el cuerpo recibido (incluida la contraseña) en errores 422.
        return JSONResponse(status_code=422, content={"detail": "Datos de solicitud no válidos"})

    app.include_router(router, responses=COMMON_ERRORS)
    if configuration.demo_mode or configuration.pitch_mode:
        app.include_router(demo_router)
        app.include_router(fleet_router)
        app.include_router(trip_router)
        app.include_router(incident_router)
        app.include_router(partner_router)
        app.include_router(delivery_router)
        if configuration.pitch_mode:
            app.include_router(pitch_router)
    else:
        app.include_router(database_health_router, responses=COMMON_ERRORS)
    return app


app = create_app()
