"""Process health and service metadata endpoints."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError
from app.db.session import get_session
from app.models import Order

router = APIRouter(tags=["health"])


class ServiceInfo(BaseModel):
    name: str
    version: str
    environment: str
    phase: int
    status: Literal["ready"]


class HealthResponse(BaseModel):
    status: Literal["ok", "ready"]


@router.get("/info", response_model=ServiceInfo)
def service_info(request: Request) -> ServiceInfo:
    """Return public build metadata used by the frontend bootstrap."""
    settings: Settings = request.app.state.settings
    return ServiceInfo(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        phase=4,
        status="ready",
    )


@router.get("/health/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    """Confirm that the HTTP process can answer requests."""
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
def readiness(session: Annotated[Session, Depends(get_session)]) -> HealthResponse:
    """Check connectivity and availability of the migrated business schema."""
    try:
        session.execute(text("SELECT 1"))
        session.execute(select(Order.id).limit(1))
    except SQLAlchemyError:
        raise AppError(
            status_code=503,
            code="database_unavailable",
            message="Database is unavailable or migrations have not been applied",
        ) from None
    return HealthResponse(status="ready")
