from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from nkz_soil.api.main import create_app

HEADERS = {"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"}
PARCEL = {
    "id": "urn:ngsi-ld:AgriParcel:parcel-1", "type": "AgriParcel",
    "location": {"type": "GeoProperty", "value": {
        "type": "Polygon",
        "coordinates": [[[-1.7, 42.7], [-1.5, 42.7], [-1.5, 42.9], [-1.7, 42.9], [-1.7, 42.7]]],
    }},
}


def _point(pid, date, horizon, parcel=True):
    e = {
        "id": f"urn:ngsi-ld:SoilSamplingPoint:{pid}", "type": "SoilSamplingPoint",
        "location": {"type": "GeoProperty",
                     "value": {"type": "Point", "coordinates": [-1.6, 42.8]}},
        "horizons": {"type": "Property", "value": horizon},  # single horizon: unwrapped
    }
    if date:
        e["samplingDate"] = {"type": "Property", "value": date}
    if parcel:
        e["hasAgriParcel"] = {"type": "Relationship", "object": PARCEL["id"]}
    return e


LINKED_OLD = _point("a", "2024-10-01", {"depthFrom": 0, "depthTo": 30, "ph": 8.0})
LINKED_NEW = _point("b", "2026-09-30", {"depthFrom": 0, "depthTo": 30,
                                        "phosphorusAvailable": 18, "phosphorusMethod": "olsen"})
GEO_ONLY = _point("c", None, {"depthFrom": 0, "depthTo": 30, "organicMatter": 2.0}, parcel=False)
PENETRO = _point("d", "2026-09-01", {"depthFrom": 0, "depthTo": 30,
                                     "penetrationResistance": 2.1})
OTHER_PARCEL = {**_point("e", "2026-10-01", {"depthFrom": 0, "depthTo": 30, "ph": 7.0}),
                "hasAgriParcel": {"type": "Relationship",
                                  "object": "urn:ngsi-ld:AgriParcel:other"}}


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def mock_orion():
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    with patch("nkz_soil.api.routes.reading.OrionClient", return_value=mock):
        yield mock


def _wire(mock, linked, by_geo, parcel=PARCEL):
    async def query(type, q=None, geometry=None, **_):
        assert type == "SoilSamplingPoint"
        return list(by_geo if geometry else linked)
    mock.query_entities = AsyncMock(side_effect=query)
    mock.get_entity = AsyncMock(return_value=parcel)


def test_lab_analyses_merged_sorted_and_filtered(client, mock_orion):
    _wire(mock_orion, [LINKED_OLD, LINKED_NEW, PENETRO], [LINKED_NEW, GEO_ONLY, PENETRO])
    resp = client.get("/v1/soil/parcel/parcel-1/lab-analyses", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["parcelId"] == "urn:ngsi-ld:AgriParcel:parcel-1"
    ids = [a["id"].split(":")[-1] for a in body["analyses"]]
    assert ids == ["b", "a", "c"]          # newest first, undated last, no penetrometer
    by_id = {a["id"].split(":")[-1]: a for a in body["analyses"]}
    assert by_id["b"]["linkedBy"] == "hasAgriParcel"
    assert by_id["c"]["linkedBy"] == "geometry"
    assert by_id["b"]["horizons"] == [{"depthFrom": 0, "depthTo": 30,
                                       "phosphorusAvailable": 18, "phosphorusMethod": "olsen"}]
    assert by_id["b"]["location"] == {"lat": 42.8, "lon": -1.6}
    assert by_id["b"]["dataSource"] == "lab_analysis"


def test_lab_analyses_unknown_parcel_is_404(client, mock_orion):
    _wire(mock_orion, [], [], parcel=None)
    resp = client.get("/v1/soil/parcel/nope/lab-analyses", headers=HEADERS)
    assert resp.status_code == 404


def test_lab_analyses_parcel_without_points_is_empty(client, mock_orion):
    _wire(mock_orion, [], [])
    resp = client.get("/v1/soil/parcel/parcel-1/lab-analyses", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["analyses"] == []


def test_geometry_fallback_skips_points_linked_to_another_parcel(client, mock_orion):
    _wire(mock_orion, [LINKED_NEW], [LINKED_NEW, OTHER_PARCEL, GEO_ONLY])
    resp = client.get("/v1/soil/parcel/parcel-1/lab-analyses", headers=HEADERS)
    ids = [a["id"].split(":")[-1] for a in resp.json()["analyses"]]
    assert ids == ["b", "c"]


def test_geometry_query_error_keeps_linked_results(client, mock_orion):
    import httpx

    async def query(type, q=None, geometry=None, **_):
        if geometry:
            req = httpx.Request("GET", "http://orion/ngsi-ld/v1/entities")
            raise httpx.HTTPStatusError("400", request=req,
                                        response=httpx.Response(400, request=req))
        return [LINKED_NEW]
    mock_orion.query_entities = AsyncMock(side_effect=query)
    mock_orion.get_entity = AsyncMock(return_value=PARCEL)
    resp = client.get("/v1/soil/parcel/parcel-1/lab-analyses", headers=HEADERS)
    assert resp.status_code == 200
    assert [a["id"].split(":")[-1] for a in resp.json()["analyses"]] == ["b"]
