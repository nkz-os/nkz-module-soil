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
    mock.create_entity = AsyncMock()
    with patch("nkz_soil.api.routes.writing.OrionClient", return_value=mock):
        yield mock


def test_create_sampling_point_valid(client, mock_orion):
    resp = client.post(
        "/v1/soil/sampling-points",
        json={
            "lat": 42.8,
            "lon": -1.6,
            "depth_from": 0,
            "depth_to": 30,
            "sand": 45,
            "silt": 35,
            "clay": 20,
            "ph": 6.8,
        },
        headers={"X-Tenant-ID": "t1"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "created"
    mock_orion.create_entity.assert_called_once()


def test_create_sampling_point_texture_sum_invalid(client, mock_orion):
    resp = client.post(
        "/v1/soil/sampling-points",
        json={
            "lat": 42.8,
            "lon": -1.6,
            "depth_from": 0,
            "depth_to": 30,
            "sand": 60,
            "silt": 60,
            "clay": 60,
        },
        headers={"X-Tenant-ID": "t1"},
    )
    assert resp.status_code == 422


def test_create_sampling_point_ph_invalid(client, mock_orion):
    resp = client.post(
        "/v1/soil/sampling-points",
        json={
            "lat": 42.8,
            "lon": -1.6,
            "depth_from": 0,
            "depth_to": 30,
            "ph": 15,
        },
        headers={"X-Tenant-ID": "t1"},
    )
    assert resp.status_code == 422


def test_create_sampling_point_bulk_density_invalid(client, mock_orion):
    resp = client.post(
        "/v1/soil/sampling-points",
        json={
            "lat": 42.8,
            "lon": -1.6,
            "depth_from": 0,
            "depth_to": 30,
            "bulk_density": 3.0,
        },
        headers={"X-Tenant-ID": "t1"},
    )
    assert resp.status_code == 422


def test_create_survey_valid(client, mock_orion):
    resp = client.post(
        "/v1/soil/surveys",
        json={"survey_type": "lab", "parcel_id": "p1"},
        headers={"X-Tenant-ID": "t1"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "created"


def test_create_survey_invalid_type(client, mock_orion):
    resp = client.post(
        "/v1/soil/surveys",
        json={"survey_type": "invalid"},
        headers={"X-Tenant-ID": "t1"},
    )
    assert resp.status_code == 422
