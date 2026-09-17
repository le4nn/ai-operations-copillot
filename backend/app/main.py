"""Minimal application entry point; backend foundation follows in phase 2."""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AI Operations Copilot", version="0.1.0")


class ServiceInfo(BaseModel):
    name: str
    phase: int
    status: str


@app.get("/api/v1/info", response_model=ServiceInfo)
def service_info() -> ServiceInfo:
    """Identify this scaffold without implying database or AI readiness."""
    return ServiceInfo(name="AI Operations Copilot", phase=1, status="scaffold")
