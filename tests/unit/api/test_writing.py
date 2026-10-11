from unittest.mock import AsyncMock, patch

import pytest
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
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
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
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
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
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
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
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
    )
    assert resp.status_code == 422


def test_create_survey_valid(client, mock_orion):
    resp = client.post(
        "/v1/soil/surveys",
        json={"survey_type": "lab", "parcel_id": "p1"},
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "created"


def test_create_survey_invalid_type(client, mock_orion):
    resp = client.post(
        "/v1/soil/surveys",
        json={"survey_type": "invalid"},
        headers={"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"},
    )
    assert resp.status_code == 422


HEADERS = {"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"}


def _no_nulls(obj):
    if isinstance(obj, dict):
        return all(v is not None and _no_nulls(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_nulls(v) for v in obj)
    return True


def test_create_sampling_point_with_fertility_and_parcel(client, mock_orion):
    resp = client.post("/v1/soil/sampling-points", json={
        "lat": 42.8, "lon": -1.6, "depth_from": 0, "depth_to": 30,
        "clay": 22, "ph": 7.9, "organic_matter": 2.1, "nitrate_n": 14,
        "phosphorus_available": 18, "phosphorus_method": "olsen",
        "potassium_exchangeable": 240, "potassium_method": "ammonium_acetate",
        "laboratory_reference": "LAB-2026-118", "sampling_date": "2026-09-30",
        "parcel_id": "parcel-1",
    }, headers=HEADERS)
    assert resp.status_code == 200
    entity = mock_orion.create_entity.call_args.args[0]
    horizon = entity["horizons"]["value"][0]
    assert horizon["organicMatter"] == 2.1
    assert horizon["phosphorusAvailable"] == 18
    assert horizon["phosphorusMethod"] == "olsen"
    assert horizon["potassiumMethod"] == "ammonium_acetate"
    assert entity["hasAgriParcel"] == {"type": "Relationship",
                                       "object": "urn:ngsi-ld:AgriParcel:parcel-1"}
    assert entity["laboratoryReference"]["value"] == "LAB-2026-118"


def test_create_sampling_point_omits_empty_optionals(client, mock_orion):
    resp = client.post("/v1/soil/sampling-points", json={
        "lat": 42.8, "lon": -1.6, "depth_from": 0, "depth_to": 30, "ph": 7.0,
    }, headers=HEADERS)
    assert resp.status_code == 200
    entity = mock_orion.create_entity.call_args.args[0]
    assert _no_nulls(entity)
    assert "samplingDate" not in entity and "hasAgriParcel" not in entity
    assert entity["horizons"]["value"][0] == {"depthFrom": 0, "depthTo": 30, "ph": 7.0}


def test_create_sampling_point_p_without_method_is_422(client, mock_orion):
    resp = client.post("/v1/soil/sampling-points", json={
        "lat": 42.8, "lon": -1.6, "depth_from": 0, "depth_to": 30,
        "phosphorus_available": 18,
    }, headers=HEADERS)
    assert resp.status_code == 422
    assert "phosphorusMethod" in resp.json()["detail"]
    mock_orion.create_entity.assert_not_called()


def test_create_sampling_point_urn_parcel_kept(client, mock_orion):
    client.post("/v1/soil/sampling-points", json={
        "lat": 42.8, "lon": -1.6, "depth_from": 0, "depth_to": 30, "ph": 7.0,
        "parcel_id": "urn:ngsi-ld:AgriParcel:abc",
    }, headers=HEADERS)
    entity = mock_orion.create_entity.call_args.args[0]
    assert entity["hasAgriParcel"]["object"] == "urn:ngsi-ld:AgriParcel:abc"


def test_create_sampling_point_non_iso_date_is_422(client, mock_orion):
    resp = client.post("/v1/soil/sampling-points", json={
        "lat": 42.8, "lon": -1.6, "depth_from": 0, "depth_to": 30, "ph": 7.0,
        "sampling_date": "15/03/2025",
    }, headers=HEADERS)
    assert resp.status_code == 422
    assert "YYYY-MM-DD" in resp.json()["detail"]
    mock_orion.create_entity.assert_not_called()


def test_create_sampling_point_fertility_requires_date(client, mock_orion):
    resp = client.post("/v1/soil/sampling-points", json={
        "lat": 42.8, "lon": -1.6, "depth_from": 0, "depth_to": 30,
        "organic_matter": 2.1,
    }, headers=HEADERS)
    assert resp.status_code == 422
    assert "samplingDate is required" in resp.json()["detail"]
