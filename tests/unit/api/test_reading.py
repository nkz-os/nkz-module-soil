import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from nkz_soil.api.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_orion():
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    mock.query_entities = AsyncMock(return_value=[])
    mock.create_entity = AsyncMock()
    with patch("nkz_soil.api.routes.reading.OrionClient", return_value=mock):
        with patch("nkz_soil.api.routes.writing.OrionClient", return_value=mock):
            yield mock


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_parcel_summary_not_found(client, mock_orion):
    mock_orion.query_entities.return_value = []
    resp = client.get("/v1/soil/parcel/test-1/summary", headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"})
    assert resp.status_code == 404


def test_parcel_summary_found(client, mock_orion):
    mock_orion.query_entities.return_value = [
        {
            "id": "urn:ngsi-ld:AgriSoil:1",
            "hasAgriParcel": {"object": "urn:ngsi-ld:AgriParcel:test-1"},
            "horizons": {"value": [{"depthFrom": 0, "depthTo": 5, "sand": 45}]},
            "dataSource": {"value": "soilgrids"},
        }
    ]
    resp = client.get("/v1/soil/parcel/test-1/summary", headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"})
    assert resp.status_code == 200
    assert resp.json()["dataSource"]["value"] == "soilgrids"


def test_parcel_horizons(client, mock_orion):
    mock_orion.query_entities.return_value = [
        {
            "id": "urn:ngsi-ld:AgriSoil:1",
            "hasAgriParcel": {"object": "urn:ngsi-ld:AgriParcel:test-1"},
            "horizons": {"value": [
                {"depthFrom": 0, "depthTo": 5, "sand": 45},
                {"depthFrom": 5, "depthTo": 15, "sand": 40},
            ]},
        }
    ]
    resp = client.get("/v1/soil/parcel/test-1/horizons?depth=0-10", headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"})
    assert resp.status_code == 200
    assert len(resp.json()["horizons"]) == 1


def test_parcel_horizons_not_found(client, mock_orion):
    mock_orion.query_entities.return_value = []
    resp = client.get("/v1/soil/parcel/test-1/horizons", headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"})
    assert resp.status_code == 404


def test_hydrologic_group(client, mock_orion):
    mock_orion.query_entities.return_value = [
        {
            "id": "urn:ngsi-ld:AgriSoil:1",
            "hasAgriParcel": {"object": "urn:ngsi-ld:AgriParcel:test-1"},
            "horizons": {"value": [{"hydrologicGroup": "B"}]},
        }
    ]
    resp = client.get("/v1/soil/parcel/test-1/hydrologic-group", headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"})
    assert resp.status_code == 200
    assert resp.json()["hydrologicGroup"] == "B"


def test_tenant_quota(client, mock_orion):
    mock_orion.query_entities.return_value = [
        {
            "id": "urn:ngsi-ld:AgriSoil:1",
            "location": {
                "value": {
                    "type": "Polygon",
                    "coordinates": [[[-2.0, 42.0], [-1.0, 42.0], [-1.0, 43.0], [-2.0, 43.0], [-2.0, 42.0]]],
                }
            },
        },
    ]
    resp = client.get("/v1/soil/tenant/quota", headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenantId"] == "tenant1"
    assert data["evaluatedHectares"] > 0
    assert data["soilEntities"] == 1


def test_tenant_quota_no_entities(client, mock_orion):
    mock_orion.query_entities.return_value = []
    resp = client.get("/v1/soil/tenant/quota", headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["evaluatedHectares"] == 0
    assert data["soilEntities"] == 0
