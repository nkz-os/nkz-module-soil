from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from nkz_soil.api.main import create_app

H = {"X-Tenant-ID": "acme", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"}
SQ = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
BOWTIE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def orion():
    m = AsyncMock()
    m.__aenter__ = AsyncMock(return_value=m)
    m.__aexit__ = AsyncMock(return_value=None)
    m.create_entity = AsyncMock()

    async def _batch(entities):
        return {"created": len(entities), "errors": [], "entity_ids": [e["id"] for e in entities]}

    m.create_entities_batch = AsyncMock(side_effect=_batch)
    with patch("nkz_soil.api.routes.writing.OrionClient", return_value=m):
        yield m


def test_sampling_point_invalidates_its_parcel(client, orion):
    with patch("nkz_soil.api.routes.writing.invalidate_parcel", AsyncMock()) as inv:
        r = client.post("/v1/soil/sampling-points", headers=H, json={
            "lat": 42.8, "lon": -1.6, "depth_from": 0, "depth_to": 30, "sand": 45, "silt": 35,
            "clay": 20, "parcel_id": "p1"})
    assert r.status_code == 200
    inv.assert_awaited_once_with("acme", "p1")


def test_batch_invalidates_each_parcel(client, orion):
    csv_body = "lat,lon,depthFrom,depthTo,sand,silt,clay,parcelId\n42.8,-1.6,0,30,45,35,20,p1\n42.8,-1.6,0,30,45,35,20,p2\n"
    with patch("nkz_soil.api.routes.writing.invalidate_parcel", AsyncMock()) as inv:
        r = client.post("/v1/soil/sampling-points/batch", headers=H,
                        files={"file": ("p.csv", csv_body, "text/csv")})
    assert r.status_code == 200
    assert sorted(c.args for c in inv.await_args_list) == [("acme", "p1"), ("acme", "p2")]


def test_invalid_geometry_is_422_naming_the_zone(client):
    body = {"parcel_id": "p1", "zones": [
        {"zoneId": "good", "zoneVersion": "v", "geometry": SQ},
        {"zoneId": "bow-tie", "zoneVersion": "v", "geometry": BOWTIE}]}
    r = client.post("/v1/soil/zonal", json=body, headers=H)
    assert r.status_code == 422 and "bow-tie" in r.text
    body["zones"][1]["geometry"] = {"type": "Polygon", "coordinates": "nonsense"}
    r = client.post("/v1/soil/zonal", json=body, headers=H)
    assert r.status_code == 422 and "bow-tie" in r.text


def test_one_failing_zone_does_not_500_the_request(client):
    soil = {"id": "x", "horizons": {"value": [{"depthFrom": 0, "depthTo": 60, "sand": 40, "silt": 40, "clay": 20}]},
            "dataSource": {"value": "soilgrids"}, "location": {"type": "GeoProperty", "value": SQ}}
    m = AsyncMock()
    m.__aenter__ = AsyncMock(return_value=m)
    m.__aexit__ = AsyncMock(return_value=None)
    m.query_entities = AsyncMock(return_value=[soil])
    from nkz_soil.services import zonal

    async def flaky(tenant, parcel, summary, zone, depth, ctx):
        if zone["zoneId"] == "z1":
            raise RuntimeError("boom")
        return {"zoneId": zone["zoneId"], "zoneVersion": zone["zoneVersion"],
                "fidelity": "zone_specific", "provider": "lab_analysis", "horizon": {}}

    body = {"parcel_id": "p1", "zones": [
        {"zoneId": f"z{i}", "zoneVersion": "v", "geometry": SQ} for i in range(3)]}
    with (
        patch("nkz_soil.api.routes.zonal.OrionClient", return_value=m),
        patch.object(zonal, "_cache_client", side_effect=RuntimeError("no redis")),
        patch.object(zonal, "_resolve_zone_soil", side_effect=flaky),
    ):
        r = client.post("/v1/soil/zonal", json=body, headers=H)
    assert r.status_code == 200
    z = r.json()["zones"]
    assert [x["fidelity"] for x in z] == ["zone_specific", "parcel_inherited", "zone_specific"]
    assert z[1]["horizon"]["sand"] == 40.0
