from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.deps import get_db
from app.core.config import settings
from app.main import app


class _UnavailableSession:
    def exec(self, *_: object, **__: object) -> None:
        raise OperationalError("readiness query", {}, ConnectionError("unavailable"))


def _unavailable_db() -> Generator[_UnavailableSession]:
    yield _UnavailableSession()


def test_readiness_check_confirms_database_and_rate_limit_schema(
    client: TestClient,
) -> None:
    response = client.get(f"{settings.API_V1_STR}/utils/readiness-check/")

    assert response.status_code == 200
    assert response.json() is True


def test_readiness_check_reports_database_or_schema_failure(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_db] = _unavailable_db
    try:
        response = client.get(f"{settings.API_V1_STR}/utils/readiness-check/")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "数据库或请求保护服务尚未就绪"
    assert response.headers["Retry-After"] == "5"
