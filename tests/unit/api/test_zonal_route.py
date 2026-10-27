from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from nkz_soil.api.main import create_app

H = {"X-Tenant-ID": "acme", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"}
SQ = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
SOIL = {
    "id": "urn:ngsi-ld:AgriSoilExtended:1",
    "horizons": {"value": [{"depthFrom": 0, "depthTo": 60, "sand": 40, "silt": 40, "clay": 20}]},
    "dataSource": {"value": "soilgrids"},
    "location": {"type": "GeoProperty", "value": SQ},
}


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def orion():
    m = AsyncMock()
    m.__aenter__ = AsyncMock(return_value=m)
    m.__aexit__ = AsyncMock(return_value=None)
    m.query_entities = AsyncMock(return_value=[SOIL])
    with patch("nkz_soil.api.routes.zonal.OrionClient", return_value=m):
        yield m


def _body(n=1):
    return {"parcel_id": "p1", "depth": "0-60", "zones": [
        {"zoneId": f"z{i}", "zoneVersion": "v1", "geometry": SQ} for i in range(n)]}


def test_returns_one_entry_per_zone(client, orion):
    async def fake(tenant, parcel, summary, zone, depth, ctx):
        assert tenant == "acme" and summary["parcelGeometry"] == SQ and depth == "0-60"
        return {"zoneId": zone["zoneId"], "zoneVersion": zone["zoneVersion"],
                "fidelity": "parcel_inherited", "provider": "soilgrids", "horizon": {}}

    with patch("nkz_soil.api.routes.zonal.resolve_zone_soil_cached", side_effect=fake):
        r = client.post("/v1/soil/zonal", json=_body(2), headers=H)
    assert r.status_code == 200
    j = r.json()
    assert j["parcel_id"] == "p1" and [z["zoneId"] for z in j["zones"]] == ["z0", "z1"]


def test_more_than_20_zones_is_422(client, orion):
    assert client.post("/v1/soil/zonal", json=_body(21), headers=H).status_code == 422


def test_no_zones_and_bad_geometry_are_422(client, orion):
    assert client.post("/v1/soil/zonal", json=_body(0), headers=H).status_code == 422
    bad = _body(1)
    bad["zones"][0]["geometry"] = {"type": "Point", "coordinates": [0, 0]}
    assert client.post("/v1/soil/zonal", json=bad, headers=H).status_code == 422


def test_unknown_parcel_is_404(client, orion):
    orion.query_entities.return_value = []
    assert client.post("/v1/soil/zonal", json=_body(1), headers=H).status_code == 404


def test_requires_gateway_headers(client, orion):
    assert client.post("/v1/soil/zonal", json=_body(1)).status_code in (401, 403)
