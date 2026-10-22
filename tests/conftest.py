import os
from unittest.mock import AsyncMock, MagicMock

import pytest

# Set required env vars for tests so config.py doesn't crash
os.environ.setdefault("ORION_BASE_URL", "http://localhost:1026")
os.environ.setdefault("ORION_LD_URL", "http://localhost:1026")
os.environ.setdefault("MINIO_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-access-key")
os.environ.setdefault("MINIO_SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("CONTEXT_URL", "http://localhost:5000/ngsi-ld-context.json")


@pytest.fixture(autouse=True)
def _mock_arq_redis(monkeypatch):
    """Avoid real Redis during API tests (lifespan opens ArqRedis pool)."""
    mock = MagicMock()
    mock.enqueue_job = AsyncMock()
    mock.close = AsyncMock()
    mock.exists = AsyncMock(return_value=0)
    mock.set = AsyncMock()
    monkeypatch.setattr("nkz_soil.api.main.ArqRedis.from_url", lambda _url: mock)


@pytest.fixture
def auth_headers():
    """Simulate api-gateway injected headers."""
    return {
        "X-Tenant-ID": "tenant1",
        "X-User-ID": "test-user-1",
        "X-User-Roles": "GestorAgricola",
    }
