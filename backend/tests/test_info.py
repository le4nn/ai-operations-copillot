from fastapi.testclient import TestClient

from app.main import app


def test_frontend_bootstrap_contract() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/info")
    assert response.status_code == 200
    assert response.json() == {"name": "AI Operations Copilot", "phase": 1, "status": "scaffold"}
