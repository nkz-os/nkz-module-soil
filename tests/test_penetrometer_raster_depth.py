"""Rasterising sampling points honours the requested depth range; reading
accepts the raster's `soilProperty` (or legacy `property`) attribute."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from nkz_soil.api.main import create_app
from nkz_soil.api.routes.writing import _sampling_value

HEADERS = {"X-Tenant-ID": "tenant-a", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"}
PROP = "penetrationResistance"


def _point(i, horizons, **root):
    e = {
        "id": f"urn:ngsi-ld:SoilSamplingPoint:{i}",
        "location": {"type": "GeoProperty",
                     "value": {"type": "Point", "coordinates": [-1.0 + i * 0.001, 42.0]}},
        "horizons": {"type": "Property", "value": horizons},
    } if horizons is not None else {
        "id": f"urn:ngsi-ld:SoilSamplingPoint:{i}",
        "location": {"type": "GeoProperty",
                     "value": {"type": "Point", "coordinates": [-1.0 + i * 0.001, 42.0]}},
    }
    e.update(root)
    return e


def _h(df, dt, v):
    return {"depthFrom": df, "depthTo": dt, PROP: v}


# --- S1: _sampling_value ---------------------------------------------------

def test_single_horizon_outside_requested_depth_is_omitted():
    e = _point(1, [_h(0, 30, 1.5)])
    assert _sampling_value(e, PROP, 30, 60) is None


def test_single_horizon_overlapping_is_used():
    e = _point(1, [_h(0, 30, 1.5)])
    assert _sampling_value(e, PROP, 0, 30) == 1.5


def test_overlapping_horizon_wins_among_several():
    e = _point(1, [_h(0, 30, 1.5), _h(30, 60, 2.5)])
    assert _sampling_value(e, PROP, 30, 60) == 2.5


def test_unwrapped_single_horizon_dict_from_orion():
    e = _point(1, None)
    e["horizons"] = {"type": "Property", "value": _h(0, 30, 1.5)}
    assert _sampling_value(e, PROP, 0, 30) == 1.5
    assert _sampling_value(e, PROP, 30, 60) is None


def test_root_value_without_horizons_and_overlapping_depth_is_used():
    e = _point(1, None, **{PROP: {"type": "Property", "value": 1.2},
                           "depthFrom": {"type": "Property", "value": 0},
                           "depthTo": {"type": "Property", "value": 30}})
    assert _sampling_value(e, PROP, 0, 30) == 1.2
    assert _sampling_value(e, PROP, 30, 60) is None


def test_root_value_without_depth_is_discarded():
    e = _point(1, None, **{PROP: {"type": "Property", "value": 1.2}})
    assert _sampling_value(e, PROP, 0, 30) is None


def test_root_value_ignored_when_horizons_exist_but_do_not_overlap():
    e = _point(1, [_h(0, 30, 1.5)], **{PROP: {"type": "Property", "value": 9.9},
                                       "depthFrom": 30, "depthTo": 60})
    assert _sampling_value(e, PROP, 30, 60) is None


# --- S1: endpoint ----------------------------------------------------------

@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def mock_orion():
    m = AsyncMock()
    m.__aenter__ = AsyncMock(return_value=m)
    m.__aexit__ = AsyncMock(return_value=None)
    m.query_entities = AsyncMock(return_value=[])
    with patch("nkz_soil.api.routes.writing.OrionClient", return_value=m), \
         patch("nkz_soil.api.routes.reading.OrionClient", return_value=m):
        yield m


def test_rasterize_three_points_same_depth_builds_raster(client, mock_orion):
    mock_orion.query_entities.return_value = [_point(i, [_h(0, 30, 1.0 + i)]) for i in range(3)]
    gen = AsyncMock(return_value={"method": "idw", "url": "u", "entity_id": "e"})
    with patch("nkz_soil.interpolation.raster.generate_raster", gen):
        r = client.post(f"/v1/soil/parcel/p1/rasterize?property={PROP}&depth=0-30", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["samplePoints"] == 3
    assert gen.await_args.kwargs["depth_from"] == 0


def test_rasterize_points_at_other_depth_are_omitted(client, mock_orion):
    mock_orion.query_entities.return_value = [_point(i, [_h(0, 30, 1.0 + i)]) for i in range(3)]
    gen = AsyncMock()
    with patch("nkz_soil.interpolation.raster.generate_raster", gen):
        r = client.post(f"/v1/soil/parcel/p1/rasterize?property={PROP}&depth=30-60", headers=HEADERS)
    assert r.status_code == 400
    gen.assert_not_awaited()


# --- S2: reading -----------------------------------------------------------

def _raster(attr):
    return {
        "id": "urn:ngsi-ld:SoilDerivedRaster:1",
        attr: {"type": "Property", "value": PROP},
        "depthFrom": {"type": "Property", "value": 0},
        "depthTo": {"type": "Property", "value": 30},
        "storageUri": {"type": "Property", "value": "s3://bkt/key.tif"},
    }


@pytest.mark.parametrize("attr", ["soilProperty", "property"])
def test_parcel_raster_reads_soil_property_and_legacy_property(client, mock_orion, attr):
    mock_orion.query_entities.return_value = [_raster(attr)]
    with patch("nkz_soil.storage.minio.get_minio_client", return_value=object()), \
         patch("nkz_soil.storage.minio.generate_presigned_url", return_value="http://signed"):
        r = client.get(f"/v1/soil/parcel/p1/raster?property={PROP}&depth=0-30", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["url"] == "http://signed"


def test_parcel_raster_other_property_is_404(client, mock_orion):
    mock_orion.query_entities.return_value = [_raster("soilProperty")]
    r = client.get("/v1/soil/parcel/p1/raster?property=ph&depth=0-30", headers=HEADERS)
    assert r.status_code == 404
