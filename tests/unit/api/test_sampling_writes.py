"""Soil analyses are written as AgriSoilSample (one entity per depth) by upsert; the API answers as before."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from nkz_soil.api.main import create_app

HEADERS = {"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"}
ZONE = "urn:ngsi-ld:AgriManagementZone:tenant1:p1:manual-1a2b3c4d-1"


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def orion():
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)

    async def _upsert(entities):
        return {"upserted": len(entities), "errors": [], "entity_ids": [e["id"] for e in entities]}

    mock.upsert_entities_batch = AsyncMock(side_effect=_upsert)
    with patch("nkz_soil.api.routes.writing.OrionClient", return_value=mock):
        yield mock


def _written(orion):
    return [e for call in orion.upsert_entities_batch.call_args_list for e in call.args[0]]


LAB_CSV = f"""lat,lon,depthFrom,depthTo,sand,silt,clay,ph,bulkDensity,labReference,samplingDate,parcelId,zoneId,numberOfSubsamples
42.8,-1.6,0,30,45,35,20,6.8,1.35,LAB-1,2026-09-01,parcel-1,{ZONE},15
42.8,-1.6,30,60,40,35,25,7.0,1.40,LAB-1,2026-09-01,parcel-1,{ZONE},15
"""


def test_post_writes_agri_soil_sample(client, orion):
    resp = client.post("/v1/soil/sampling-points", json={
        "lat": 42.8, "lon": -1.6, "depth_from": 0, "depth_to": 30, "sand": 45, "silt": 35, "clay": 20,
        "ph": 6.8, "sampling_date": "2026-09-01", "parcel_id": "parcel-1",
    }, headers=HEADERS)
    assert resp.status_code == 200
    (e,) = _written(orion)
    assert resp.json() == {"id": e["id"], "status": "created"}
    assert e["type"] == "AgriSoilSample" and e["id"].startswith("urn:ngsi-ld:AgriSoilSample:tenant1:")
    assert e["sand"]["value"] == 0.45 and e["soilPh"]["value"] == 6.8 and e["depthTo"]["value"] == 0.3
    assert e["hasAgriParcel"]["object"] == "urn:ngsi-ld:AgriParcel:parcel-1"


def test_post_accepts_zone_and_subsamples(client, orion):
    resp = client.post("/v1/soil/sampling-points", json={
        "lat": 42.8, "lon": -1.6, "depth_from": 0, "depth_to": 30, "ph": 6.8,
        "zone_id": ZONE, "number_of_subsamples": 12,
    }, headers=HEADERS)
    assert resp.status_code == 200
    (e,) = _written(orion)
    assert e["hasAgriManagementZone"]["object"] == ZONE and e["numberOfSubsamples"]["value"] == 12


def test_post_rejects_a_zone_that_is_not_a_zone_urn(client, orion):
    resp = client.post("/v1/soil/sampling-points", json={
        "lat": 42.8, "lon": -1.6, "depth_from": 0, "depth_to": 30, "ph": 6.8, "zone_id": "Z1",
    }, headers=HEADERS)
    assert resp.status_code == 422 and "zoneId" in resp.json()["detail"]
    orion.upsert_entities_batch.assert_not_called()


def test_batch_writes_one_entity_per_depth(client, orion):
    resp = client.post("/v1/soil/sampling-points/batch",
                       files={"file": ("lab.csv", LAB_CSV, "text/csv")}, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert (data["created"], data["errors"], data["method"]) == (2, 0, "batch")
    assert [d["row"] for d in data["details"]] == [2, 3]
    top, sub = _written(orion)
    assert {top["type"], sub["type"]} == {"AgriSoilSample"}
    assert (top["depthFrom"]["value"], sub["depthFrom"]["value"]) == (0, 0.3)
    assert top["bulkDensity"]["value"] == 1350 and top["hasAgriManagementZone"]["object"] == ZONE
    assert top["numberOfSubsamples"]["value"] == 15 and top["sampleCode"]["value"] == "LAB-1"


def test_reimport_is_idempotent(client, orion):
    for _ in range(2):
        client.post("/v1/soil/sampling-points/batch",
                    files={"file": ("lab.csv", LAB_CSV, "text/csv")}, headers=HEADERS)
    first, second = orion.upsert_entities_batch.call_args_list
    assert [e["id"] for e in first.args[0]] == [e["id"] for e in second.args[0]]
    orion.create_entities_batch.assert_not_called()


def test_batch_rejects_bad_zone_and_subsamples(client, orion):
    csv = ("lat,lon,depthFrom,depthTo,ph,zoneId,numberOfSubsamples\n"
           "42.8,-1.6,0,30,7.0,zone-1,\n"
           "42.8,-1.6,0,30,7.0,,0\n"
           "42.8,-1.6,0,30,7.0,,abc\n")
    data = client.post("/v1/soil/sampling-points/batch",
                       files={"file": ("x.csv", csv, "text/csv")}, headers=HEADERS).json()
    assert data["created"] == 0 and data["errors"] == 3
    assert "zoneId" in data["errorDetails"][0]["error"]
    assert "numberOfSubsamples" in data["errorDetails"][1]["error"]
    assert "numberOfSubsamples" in data["errorDetails"][2]["error"]


def test_batch_reports_broker_errors_per_row(client, orion):
    async def _partial(entities):
        return {"upserted": 1, "entity_ids": [entities[0]["id"]],
                "errors": [{"entityId": entities[1]["id"], "error": {"title": "Bad Request"}}]}
    orion.upsert_entities_batch.side_effect = _partial
    data = client.post("/v1/soil/sampling-points/batch",
                       files={"file": ("lab.csv", LAB_CSV, "text/csv")}, headers=HEADERS).json()
    assert data["created"] == 1 and data["errors"] == 1
    assert data["errorDetails"][0]["row"] == 3
