"""Acceso compartido al pitch y reinicio reservado al presentador."""

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import delete, insert, select, update

from app.models import PitchScenario, PitchSession
from app.pitch_seed import prepared_scenario
from app.pitch_state import check_schema, dump_store, scenario_row
from app.security import create_token, token_digest

pitch_router = APIRouter(prefix="/api/v1/pitch", tags=["pitch preparado"])


class PitchLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_key: SecretStr = Field(min_length=1, max_length=256)


class PitchReset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reset_key: SecretStr = Field(min_length=1, max_length=256)
    expected_generation: uuid.UUID
    confirmation: str = Field(pattern=r"^REINICIAR$")


class PitchToken(BaseModel):
    access_token: str
    expires_at: datetime


def require_pitch_session(request: Request) -> str:
    prefix, _, token = request.headers.get("Authorization", "").partition(" ")
    if prefix.lower() != "bearer" or not token or len(token) > 256:
        raise HTTPException(
            401, "Introduce la clave de acceso al pitch", headers={"WWW-Authenticate": "Bearer"}
        )
    settings = request.app.state.settings
    with request.app.state.engine.connect() as connection:
        exists = connection.scalar(
            select(PitchSession.token_hash).where(
                PitchSession.token_hash == token_digest(token),
                PitchSession.scenario_id == settings.pitch_scenario_id,
                PitchSession.expires_at > datetime.now(UTC),
            )
        )
    if exists is None:
        raise HTTPException(
            401, "La sesión del pitch venció o fue cerrada", headers={"WWW-Authenticate": "Bearer"}
        )
    return token_digest(token)


@pitch_router.post("/login", response_model=PitchToken)
def pitch_login(data: PitchLogin, request: Request) -> PitchToken:
    settings = request.app.state.settings
    if not secrets.compare_digest(
        data.access_key.get_secret_value().encode(),
        settings.pitch_access_key.get_secret_value().encode(),
    ):
        raise HTTPException(401, "Clave de acceso no válida")
    token, expires_at = create_token(settings.session_ttl_minutes)
    with request.app.state.engine.begin() as connection:
        check_schema(connection)
        scenario_row(connection, settings.pitch_scenario_id)
        connection.execute(
            delete(PitchSession).where(
                PitchSession.scenario_id == settings.pitch_scenario_id,
                PitchSession.expires_at <= datetime.now(UTC),
            )
        )
        connection.execute(
            insert(PitchSession).values(
                token_hash=token_digest(token),
                scenario_id=settings.pitch_scenario_id,
                expires_at=expires_at,
            )
        )
    return PitchToken(access_token=token, expires_at=expires_at)


@pitch_router.post("/logout", status_code=204)
def pitch_logout(request: Request, token_hash: str = Depends(require_pitch_session)) -> Response:
    with request.app.state.engine.begin() as connection:
        connection.execute(delete(PitchSession).where(PitchSession.token_hash == token_hash))
    return Response(status_code=204)


@pitch_router.post("/reset")
def pitch_reset(
    data: PitchReset, request: Request, token_hash: str = Depends(require_pitch_session)
) -> dict:
    settings = request.app.state.settings
    if not secrets.compare_digest(
        data.reset_key.get_secret_value().encode(),
        settings.pitch_reset_key.get_secret_value().encode(),
    ):
        raise HTTPException(403, "Clave del presentador no válida")
    payload = dump_store(prepared_scenario())
    generation = uuid.uuid4()
    with request.app.state.engine.begin() as connection:
        row = scenario_row(connection, settings.pitch_scenario_id, lock=True)
        if row["generation"] != data.expected_generation:
            raise HTTPException(409, "El escenario ya cambió; actualiza antes de reiniciarlo")
        connection.execute(
            update(PitchScenario)
            .where(PitchScenario.id == settings.pitch_scenario_id)
            .values(generation=generation, payload=payload, updated_at=datetime.now(UTC))
        )
    return {"scenario_generation": str(generation), "scenario_name": "Monami · Pitch preparado"}
