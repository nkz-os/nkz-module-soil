"""Tests for the CSV batch upload endpoint."""

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

    async def _batch_create(entities):
        return {
            "created": len(entities),
            "errors": [],
            "entity_ids": [e["id"] for e in entities],
        }

    mock.create_entities_batch = AsyncMock(side_effect=_batch_create)
    with patch("nkz_soil.api.routes.writing.OrionClient", return_value=mock):
        yield mock


VALID_CSV = """lat,lon,depthFrom,depthTo,sand,silt,clay,ph
42.8,-1.6,0,30,45,35,20,6.8
42.9,-1.5,0,15,60,20,20,7.2
"""

INVALID_TEXTURE_CSV = """lat,lon,depthFrom,depthTo,sand,silt,clay
42.8,-1.6,0,30,60,60,60
"""

MISSING_HEADERS_CSV = """name,value
foo,bar
"""


def test_csv_batch_valid(client, mock_orion):
    resp = client.post(
        "/v1/soil/sampling-points/batch",
        files={"file": ("soil.csv", VALID_CSV, "text/csv")},
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 2
    assert data["errors"] == 0
    assert mock_orion.create_entities_batch.call_count == 1


def test_csv_batch_invalid_texture(client, mock_orion):
    resp = client.post(
        "/v1/soil/sampling-points/batch",
        files={"file": ("bad.csv", INVALID_TEXTURE_CSV, "text/csv")},
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 0
    assert data["errors"] == 1
    assert "sand+silt+clay" in data["errorDetails"][0]["error"]


def test_csv_batch_missing_headers(client, mock_orion):
    resp = client.post(
        "/v1/soil/sampling-points/batch",
        files={"file": ("bad.csv", MISSING_HEADERS_CSV, "text/csv")},
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
    )
    assert resp.status_code == 422
    assert "lat" in resp.json()["detail"]


def test_csv_batch_not_csv(client, mock_orion):
    resp = client.post(
        "/v1/soil/sampling-points/batch",
        files={"file": ("data.txt", b"not a csv", "text/plain")},
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
    )
    assert resp.status_code == 422


def test_csv_batch_mixed_valid_invalid(client, mock_orion):
    mixed_csv = """lat,lon,depthFrom,depthTo,sand,silt,clay,ph
42.8,-1.6,0,30,45,35,20,6.8
42.9,-1.5,0,30,60,60,60,7.0
43.0,-1.4,5,15,30,50,20,6.5
"""
    resp = client.post(
        "/v1/soil/sampling-points/batch",
        files={"file": ("mixed.csv", mixed_csv, "text/csv")},
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 2
    assert data["errors"] == 1
    assert mock_orion.create_entities_batch.call_count == 1


def test_csv_batch_with_aliases(client, mock_orion):
    """Test CSV with snake_case column aliases."""
    aliased_csv = """lat,lon,depth_from,depth_to,sand,silt,clay,organic_carbon,bulk_density
42.8,-1.6,0,30,45,35,20,2.1,1.32
"""
    resp = client.post(
        "/v1/soil/sampling-points/batch",
        files={"file": ("aliased.csv", aliased_csv, "text/csv")},
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 1
    assert data["errors"] == 0
