from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from nkz_soil.api.main import app

client = TestClient(app)


def _mock_orion(entities):
    m = MagicMock()
    m.__aenter__ = AsyncMock(return_value=m)
    m.__aexit__ = AsyncMock(return_value=None)
    m.query_entities = AsyncMock(return_value=entities)
    return m


def test_rejects_disallowed_attribute():
    r = client.get("/v1/soil/layers/parcels.geojson?attribute=clay",
                   headers={"X-Tenant-ID": "t1"})
    assert r.status_code == 400


def test_returns_featurecollection():
    geom = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]}
    ent = {"id": "urn:ngsi-ld:AgriSoilExtended:p1",
           "refAgriParcel": {"object": "urn:ngsi-ld:AgriParcel:p1"},
           "location": {"value": geom},
           "horizons": {"value": [{"depthFrom": 0, "depthTo": 5, "hydrologicGroup": "B"}]}}
    with patch("nkz_soil.api.routes.layers.OrionClient", return_value=_mock_orion([ent])):
        r = client.get("/v1/soil/layers/parcels.geojson?attribute=hydrologicGroup",
                       headers={"X-Tenant-ID": "t1"})
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"][0]["properties"]["value"] == "B"
