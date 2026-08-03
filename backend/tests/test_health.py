from fastapi.testclient import TestClient

from app.api.v1.health import get_db
from app.main import app


def test_liveness_endpoint_returns_ok() -> None:
    response = TestClient(app).get("/api/v1/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "not-checked"}


def test_readiness_endpoint_checks_database() -> None:
    class ReadyDatabase:
        executed_statement: str | None = None

        async def execute(self, statement: object) -> None:
            self.executed_statement = str(statement)

    database = ReadyDatabase()

    async def override_get_db():
        yield database  # type: ignore[misc]

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).get("/api/v1/readyz")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}
    assert database.executed_statement == "SELECT 1"
