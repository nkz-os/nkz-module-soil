"""Tests for GET /v1/soil/parcel/{id}/compaction-susceptibility endpoint."""

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
        yield mock


MOCK_AGRI_SOIL = {
    "id": "urn:ngsi-ld:AgriSoilExtended:test-tenant:parcel-42",
    "type": "AgriSoilExtended",
    "hasAgriParcel": {
        "type": "Relationship",
        "object": "urn:ngsi-ld:AgriParcel:parcel-42",
    },
    "horizons": {
        "type": "Property",
        "value": [
            {
                "depthFrom": 0,
                "depthTo": 30,
                "sand": 30,
                "clay": 35,
                "silt": 35,
                "compactionSusceptibility": {
                    "score": 65,
                    "class": "high",
                    "texturalScore": 65,
                    "modifiersApplied": ["organic_matter_low_5"],
                    "indicativeElevatedBd": True,
                },
            },
            {
                "depthFrom": 30,
                "depthTo": 60,
                "sand": 25,
                "clay": 40,
                "silt": 35,
                "compactionSusceptibility": {
                    "score": 72,
                    "class": "very_high",
                    "texturalScore": 70,
                    "modifiersApplied": [],
                    "indicativeElevatedBd": False,
                },
            },
        ],
    },
    "compactionSusceptibility": {
        "type": "Property",
        "value": {
            "overallScore": 68,
            "overallClass": "very_high",
            "worstHorizonScore": 72,
            "worstHorizonClass": "very_high",
        },
    },
}


def test_endpoint_returns_susceptibility(client, mock_orion):
    mock_orion.query_entities.return_value = [MOCK_AGRI_SOIL]
    response = client.get(
        "/v1/soil/parcel/parcel-42/compaction-susceptibility",
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["parcelId"] == "parcel-42"
    assert data["overall"]["score"] == 68
    assert data["overall"]["class"] == "very_high"
    assert len(data["byHorizon"]) == 2
    assert data["byHorizon"][0]["class"] == "high"
    assert data["byHorizon"][1]["class"] == "very_high"


def test_endpoint_404_when_no_soil_data(client, mock_orion):
    mock_orion.query_entities.return_value = []
    response = client.get(
        "/v1/soil/parcel/nonexistent/compaction-susceptibility",
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
    )
    assert response.status_code == 404
    assert "No AgriSoil found" in response.json()["detail"]


def test_endpoint_handles_missing_susceptibility_data(client, mock_orion):
    """Horizon without compactionSusceptibility should not crash."""
    soil_without_cs = {
        **MOCK_AGRI_SOIL,
        "horizons": {
            "type": "Property",
            "value": [
                {
                    "depthFrom": 0,
                    "depthTo": 30,
                    "sand": 40,
                    "clay": 20,
                    "silt": 40,
                    # no compactionSusceptibility key
                }
            ],
        },
    }
    mock_orion.query_entities.return_value = [soil_without_cs]
    response = client.get(
        "/v1/soil/parcel/parcel-42/compaction-susceptibility",
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["byHorizon"] == []  # no susceptibility data in any horizon
