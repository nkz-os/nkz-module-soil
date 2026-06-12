"""Tests for the internal service-to-service endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from nkz_soil.api.main import app


@pytest.fixture
def with_secret(monkeypatch):
    """Patch INTERNAL_SERVICE_SECRET on the internal module.

    The internal module imports INTERNAL_SERVICE_SECRET from config at module
    level (copy), so we must patch the destination module directly.

    The _mock_arq_redis autouse fixture (in conftest.py) imports
    nkz_soil.api.main which runs app = create_app() and loads the internal
    module BEFORE this fixture runs.
    """
    monkeypatch.setattr(
        "nkz_soil.api.routes.internal.INTERNAL_SERVICE_SECRET",
        "test-secret-123",
    )
    yield


@pytest.mark.asyncio
async def test_setup_parcel_missing_secret_returns_403(with_secret):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/soil/internal/setup-parcel",
            json={"parcelId": "test123", "tenantId": "tenant1"},
        )
    assert resp.status_code == 403
    assert "Invalid internal service secret" in resp.text


@pytest.mark.asyncio
async def test_setup_parcel_wrong_secret_returns_403(with_secret):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/soil/internal/setup-parcel",
            json={"parcelId": "test123", "tenantId": "tenant1"},
            headers={"X-Internal-Service-Secret": "wrong-secret"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_setup_parcel_missing_body_fields_returns_422(with_secret):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/soil/internal/setup-parcel",
            json={"parcelId": ""},
            headers={"X-Internal-Service-Secret": "test-secret-123"},
        )
    assert resp.status_code == 422
