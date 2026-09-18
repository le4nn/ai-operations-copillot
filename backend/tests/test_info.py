import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.exceptions import ResourceNotFoundError
from app.core.handlers import register_exception_handlers
from app.core.logging import JsonFormatter
from app.main import create_app


def build_client() -> TestClient:
    settings = Settings(environment="test", log_level="CRITICAL")
    return TestClient(create_app(settings))


def test_service_info() -> None:
    with build_client() as client:
        response = client.get("/api/v1/info")

    assert response.status_code == 200
    assert response.json() == {
        "name": "AI Operations Copilot",
        "version": "0.2.0",
        "environment": "test",
        "phase": 2,
        "status": "ready",
    }
    assert response.headers["X-Request-ID"]


def test_health_endpoints_have_distinct_semantics() -> None:
    with build_client() as client:
        live = client.get("/api/v1/health/live")
        ready = client.get("/api/v1/health/ready")

    assert live.json() == {"status": "ok"}
    assert ready.json() == {"status": "ready"}


def test_safe_request_id_is_propagated() -> None:
    with build_client() as client:
        response = client.get("/api/v1/health/live", headers={"X-Request-ID": "demo-request-123"})

    assert response.headers["X-Request-ID"] == "demo-request-123"


def test_unsafe_request_id_is_replaced() -> None:
    with build_client() as client:
        response = client.get("/api/v1/health/live", headers={"X-Request-ID": "bad value"})

    assert response.headers["X-Request-ID"] != "bad value"


def test_expected_error_uses_public_envelope() -> None:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/missing")
    def missing() -> None:
        raise ResourceNotFoundError("order", 42)

    with TestClient(test_app) as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"
    assert response.json()["error"]["message"] == "order with id '42' was not found"


def test_unexpected_error_does_not_leak_details() -> None:
    test_app = create_app(Settings(environment="test", log_level="CRITICAL"))

    @test_app.get("/broken")
    def broken() -> None:
        raise RuntimeError("database password must never reach a client")

    with TestClient(test_app) as client:
        response = client.get("/broken", headers={"X-Request-ID": "failed-request-42"})

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["request_id"] == "failed-request-42"
    assert response.headers["X-Request-ID"] == "failed-request-42"
    assert "password" not in body["error"]["message"]


def test_json_formatter_includes_context() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", (), None)
    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "hello"
    assert payload["request_id"] == "system"
