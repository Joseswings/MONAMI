from collections.abc import Iterator

from fastapi import HTTPException, Request
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session


def build_engine(url: SecretStr) -> Engine:
    return create_engine(
        url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        hide_parameters=True,
        connect_args={"connect_timeout": 5, "prepare_threshold": None},
    )


def get_db(request: Request) -> Iterator[Session]:
    engine = request.app.state.engine
    if engine is None:
        raise HTTPException(503, "Servicio de datos no disponible")
    with Session(engine) as session:
        yield session
