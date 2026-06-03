"""Auth regression tests — require gateway headers on protected routes."""

import pytest
from fastapi.testclient import TestClient

from nkz_soil.api.dependencies import gateway_auth_headers
from nkz_soil.api.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_summary_requires_user_id(client):
    resp = client.get(
        "/v1/soil/parcel/p1/summary",
        headers={"X-Tenant-ID": "tenant1"},
    )
    assert resp.status_code == 401


def test_summary_with_gateway_headers(client):
    from unittest.mock import AsyncMock, patch

    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    mock.query_entities = AsyncMock(return_value=[])

    with patch("nkz_soil.api.routes.reading.OrionClient", return_value=mock):
        resp = client.get(
            "/v1/soil/parcel/p1/summary",
            headers=gateway_auth_headers(tenant_id="tenant1"),
        )
    assert resp.status_code == 404


def test_webhook_rejects_missing_tenant(client):
    resp = client.post(
        "/v1/soil/webhooks/orion",
        json={
            "subscriptionId": "urn:ngsi-ld:Subscription:soil-parcel-ingest",
            "type": "AgriParcel",
            "data": [
                {
                    "id": "urn:ngsi-ld:AgriParcel:x",
                    "location": {"value": {"type": "Point", "coordinates": [0, 0]}},
                }
            ],
        },
    )
    assert resp.status_code == 400


def test_webhook_ignores_unknown_subscription(client):
    resp = client.post(
        "/v1/soil/webhooks/orion",
        headers={"NGSILD-Tenant": "t1"},
        json={
            "subscriptionId": "urn:ngsi-ld:Subscription:other",
            "type": "AgriParcel",
            "data": [{"id": "urn:ngsi-ld:AgriParcel:x", "location": {"value": {"type": "Point", "coordinates": [0, 0]}}}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_health_no_auth_required(client):
    resp = client.get("/health")
    assert resp.status_code == 200
