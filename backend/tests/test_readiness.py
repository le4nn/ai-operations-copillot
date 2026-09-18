from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_session
from app.main import create_app


def test_readiness_with_migrated_database(database):
    app = create_app(Settings(environment="test", log_level="CRITICAL"))

    def session_override():
        with Session(database) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        assert client.get("/api/v1/health/ready").json() == {"status": "ready"}
