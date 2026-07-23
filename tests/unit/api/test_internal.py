"""Tests for the internal service-to-service endpoints."""

from unittest.mock import AsyncMock, patch

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
            json={"parcel_id": "test123", "tenant_id": "tenant1"},
        )
    assert resp.status_code == 403
    assert "Invalid internal service secret" in resp.text


@pytest.mark.asyncio
async def test_setup_parcel_wrong_secret_returns_403(with_secret):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/soil/internal/setup-parcel",
            json={"parcel_id": "test123", "tenant_id": "tenant1"},
            headers={"X-Internal-Service-Secret": "wrong-secret"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_setup_parcel_missing_body_fields_returns_422(with_secret):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/soil/internal/setup-parcel",
            json={"parcel_id": ""},
            headers={"X-Internal-Service-Secret": "test-secret-123"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_setup_parcel_happy_path_with_geometry(with_secret):
    """Happy path: valid secret + geometry → 202 + enqueued job."""
    from unittest.mock import AsyncMock

    redis_mock = AsyncMock()
    redis_mock.enqueue_job = AsyncMock(return_value=None)
    app.state.redis = redis_mock

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/soil/internal/setup-parcel",
                json={
                    "parcel_id": "test123",
                    "tenant_id": "tenant1",
                    "geometry": {"type": "Point", "coordinates": [-2.0, 42.0]},
                },
                headers={"X-Internal-Service-Secret": "test-secret-123"},
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["parcelId"] == "test123"
        assert data["status"] == "accepted"
        redis_mock.enqueue_job.assert_awaited_once()
    finally:
        app.state.redis = None


@pytest.mark.asyncio
async def test_setup_parcel_resolves_geometry_from_orion_when_absent(with_secret):
    """Regression: the fallback used q='id=="..."', which NGSI-LD's `q`
    grammar doesn't support (id isn't a queryable attribute) — it always
    returned zero results, so every real activation without an inline
    geometry 404'd with "Cannot resolve geometry", even for parcels that
    have one. Fixed by fetching the entity directly by id instead.
    """
    from unittest.mock import AsyncMock

    redis_mock = AsyncMock()
    redis_mock.enqueue_job = AsyncMock(return_value=None)
    app.state.redis = redis_mock

    mock_orion = AsyncMock()
    mock_orion.__aenter__ = AsyncMock(return_value=mock_orion)
    mock_orion.__aexit__ = AsyncMock(return_value=None)
    mock_orion.get_entity = AsyncMock(
        return_value={
            "id": "urn:ngsi-ld:AgriParcel:test123",
            "location": {
                "type": "GeoProperty",
                "value": {"type": "Point", "coordinates": [-2.0, 42.0]},
            },
        }
    )

    transport = ASGITransport(app=app)
    try:
        with patch("nkz_soil.api.routes.internal.OrionClient", return_value=mock_orion):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/soil/internal/setup-parcel",
                    json={"parcel_id": "test123", "tenant_id": "tenant1"},
                    headers={"X-Internal-Service-Secret": "test-secret-123"},
                )
        assert resp.status_code == 202
        mock_orion.get_entity.assert_awaited_once_with("urn:ngsi-ld:AgriParcel:test123")
        redis_mock.enqueue_job.assert_awaited_once()
    finally:
        app.state.redis = None


@pytest.mark.asyncio
async def test_setup_parcel_returns_404_when_entity_has_no_location(with_secret):
    mock_orion = AsyncMock()
    mock_orion.__aenter__ = AsyncMock(return_value=mock_orion)
    mock_orion.__aexit__ = AsyncMock(return_value=None)
    mock_orion.get_entity = AsyncMock(return_value=None)

    transport = ASGITransport(app=app)
    with patch("nkz_soil.api.routes.internal.OrionClient", return_value=mock_orion):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/soil/internal/setup-parcel",
                json={"parcel_id": "test123", "tenant_id": "tenant1"},
                headers={"X-Internal-Service-Secret": "test-secret-123"},
            )
    assert resp.status_code == 404
