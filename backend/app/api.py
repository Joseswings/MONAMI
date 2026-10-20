from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SCHEMA_REVISION, AuthSession, Organization, Role, User
from app.schemas import (
    ErrorOutput,
    HealthOutput,
    IdentityOutput,
    LoginInput,
    LoginOutput,
    OrganizationOutput,
)
from app.security import create_token, token_digest, verify_password

router = APIRouter()
database_health_router = APIRouter()
DB = Annotated[Session, Depends(get_db)]
bearer = HTTPBearer(auto_error=False)


def unauthorized() -> HTTPException:
    return HTTPException(
        401, "Credenciales o sesión no válidas", headers={"WWW-Authenticate": "Bearer"}
    )


@dataclass
class Principal:
    user: User
    organization: Organization
    session: AuthSession


def current_principal(
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    if credentials is None or len(credentials.credentials) > 256:
        raise unauthorized()
    row = db.execute(
        select(User, Organization, AuthSession)
        .join(AuthSession, AuthSession.user_id == User.id)
        .join(Organization, Organization.id == User.organization_id)
        .where(
            AuthSession.token_hash == token_digest(credentials.credentials),
            AuthSession.expires_at > datetime.now(UTC),
            User.is_active.is_(True),
        )
    ).first()
    if row is None:
        raise unauthorized()
    return Principal(*row)


Authenticated = Annotated[Principal, Depends(current_principal)]


def company_principal(principal: Authenticated) -> Principal:
    if principal.user.role != Role.COMPANY.value:
        raise HTTPException(403, "Esta operación requiere el rol empresa")
    return principal


@router.get("/health/live", response_model=HealthOutput, tags=["health"])
def live() -> HealthOutput:
    return HealthOutput(status="ok")


@database_health_router.get("/health/ready", response_model=HealthOutput, tags=["health"])
def ready(db: DB) -> HealthOutput:
    revision = db.scalar(text("SELECT version_num FROM public.monami_schema_version"))
    if revision != SCHEMA_REVISION:
        raise HTTPException(503, "Servicio de datos no disponible")
    # Verifica también tablas/columnas y permisos SELECT, sin leer datos personales.
    for model in (Organization, User, AuthSession):
        db.execute(select(model).limit(0))
    return HealthOutput(status="ready")


@router.post("/api/v1/auth/login", response_model=LoginOutput, tags=["auth"])
def login(payload: LoginInput, request: Request, response: Response, db: DB) -> LoginOutput:
    response.headers["Cache-Control"] = "no-store"
    user = db.scalar(select(User).where(User.email == payload.email))
    if not verify_password(
        payload.password.get_secret_value(), user.password_hash if user is not None else None
    ):
        raise unauthorized()
    if user is None or not user.is_active:
        raise unauthorized()
    token, expires_at = create_token(request.app.state.settings.session_ttl_minutes)
    db.add(AuthSession(token_hash=token_digest(token), user_id=user.id, expires_at=expires_at))
    db.commit()
    return LoginOutput(access_token=token, expires_at=expires_at)


@router.post("/api/v1/auth/logout", status_code=204, tags=["auth"])
def logout(principal: Authenticated, db: DB) -> Response:
    db.execute(delete(AuthSession).where(AuthSession.token_hash == principal.session.token_hash))
    db.commit()
    return Response(status_code=204)


@router.get("/api/v1/me", response_model=IdentityOutput, tags=["identity"])
def me(principal: Authenticated) -> IdentityOutput:
    return IdentityOutput(
        id=principal.user.id,
        name=principal.user.name,
        email=principal.user.email,
        role=Role(principal.user.role),
        organization=OrganizationOutput.model_validate(principal.organization),
    )


@router.get("/api/v1/company", response_model=OrganizationOutput, tags=["identity"])
def company(principal: Annotated[Principal, Depends(company_principal)]) -> Organization:
    return principal.organization


COMMON_ERRORS = {
    401: {"model": ErrorOutput, "description": "Autenticación requerida o sesión no válida"},
    403: {"model": ErrorOutput, "description": "Permisos insuficientes"},
    503: {"model": ErrorOutput, "description": "Servicio de datos no disponible"},
}
