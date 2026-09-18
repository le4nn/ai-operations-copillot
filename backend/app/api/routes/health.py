"""Process health and service metadata endpoints."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.config import Settings

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
        phase=2,
        status="ready",
    )


@router.get("/health/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    """Confirm that the HTTP process can answer requests."""
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
def readiness() -> HealthResponse:
    """Confirm current dependencies are ready.

    Phase 2 has no external runtime dependencies. Database and Redis checks will
    be added when those dependencies become part of request handling.
    """
    return HealthResponse(status="ready")
