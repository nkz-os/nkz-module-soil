"""Per-zone soil resolution: the first source that resolves INSIDE the zone wins,
otherwise the parcel value is returned, flagged parcel_inherited."""
import io
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from nkz_soil.providers.idena import IdenaProvider
from nkz_soil.services import zonal


def _square(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def _recinto(x0, y0, x1, y1, hs1):
    return {
        "type": "Feature",
        "geometry": _square(x0, y0, x1, y1),
        "properties": {"CLASIF_HS1": hs1},
    }


PARCEL_GEOM = _square(-1.60, 42.80, -1.58, 42.82)
ZONE_A = {"zoneId": "z1", "zoneVersion": "v1", "geometry": _square(-1.60, 42.80, -1.59, 42.81)}
ZONE_B = {"zoneId": "z2", "zoneVersion": "v1", "geometry": _square(-1.59, 42.81, -1.58, 42.82)}

PARCEL_SUMMARY = {
    "horizons": [{
        "depthFrom": 0, "depthTo": 60, "sand": 40.0, "silt": 40.0, "clay": 20.0,
        "organicCarbon": 1.2, "ph": 7.5, "fieldCapacity": 0.27, "wiltingPoint": 0.14,
        "availableWaterCapacity": 0.13, "ksatSaturated": 12.0,
        "hydrologicGroup": "B", "usdaTextureClass": "loam",
    }],
    "dataSource": {"type": "Property", "value": "soilgrids"},
    "parcelGeometry": PARCEL_GEOM,
}


@pytest.fixture
def no_sources():
    """Every zone-level source empty; individual tests override one."""
    with (
        patch.object(zonal, "_sampling_points_in_zone", AsyncMock(return_value=[])),
        patch.object(zonal, "_raster_values_in_zone", AsyncMock(return_value=None)),
        patch.object(IdenaProvider, "features_for_bbox", AsyncMock(return_value=[])),
        patch.object(zonal, "_lucas_in_zone", AsyncMock(return_value=None)),
    ):
        yield


def _point(sand, silt, clay, oc, ph=6.8):
    return {"horizons": {"type": "Property", "value": [{
        "depthFrom": 0, "depthTo": 30, "sand": sand, "silt": silt, "clay": clay,
        "organicCarbon": oc, "ph": ph,
    }]}}


@pytest.mark.asyncio
async def test_sampling_point_in_zone_a_only(no_sources):
    with patch.object(zonal, "_sampling_points_in_zone", AsyncMock(
        side_effect=lambda tenant, geom: [_point(60, 25, 15, 0.9)] if geom == ZONE_A["geometry"] else []
    )):
        a = await zonal.resolve_zone_soil("acme", "p1", PARCEL_SUMMARY, ZONE_A)
        b = await zonal.resolve_zone_soil("acme", "p1", PARCEL_SUMMARY, ZONE_B)
    assert (a["provider"], a["fidelity"]) == ("lab_analysis", "zone_specific")
    assert a["horizon"]["sand"] == 60 and a["horizon"]["clay"] == 15
    assert a["horizon"]["ph"] == 6.8
    assert a["horizon"]["fieldCapacity"] is not None  # pedotransfer applied
    assert a["horizon"]["usdaTextureClass"] == "sandy-loam"
    assert (b["provider"], b["fidelity"]) == ("soilgrids", "parcel_inherited")


@pytest.mark.asyncio
async def test_lab_points_are_averaged(no_sources):
    pts = [_point(60, 30, 10, 1.0), _point(40, 30, 30, 2.0)]
    with patch.object(zonal, "_sampling_points_in_zone", AsyncMock(return_value=pts)):
        a = await zonal.resolve_zone_soil("acme", "p1", PARCEL_SUMMARY, ZONE_A)
    assert a["horizon"]["sand"] == 50 and a["horizon"]["clay"] == 20
    assert a["horizon"]["organicCarbon"] == 1.5


@pytest.mark.asyncio
async def test_raster_beats_idena(no_sources):
    vals = {"sand": 70.0, "silt": 20.0, "clay": 10.0, "organic_carbon": 0.8}
    with patch.object(zonal, "_raster_values_in_zone", AsyncMock(return_value=vals)):
        a = await zonal.resolve_zone_soil("acme", "p1", PARCEL_SUMMARY, ZONE_A)
    assert (a["provider"], a["fidelity"]) == ("derived_raster", "zone_specific")
    assert a["horizon"]["sand"] == 70


def _two_class_features():
    # West half of the parcel clay, east half sandy loam; ZONE_A sits in the west.
    return [
        _recinto(-1.60, 42.80, -1.59, 42.82, "Arcillosa"),
        _recinto(-1.59, 42.80, -1.58, 42.82, "Franco arenosa"),
    ]


@pytest.mark.asyncio
async def test_idena_two_classes_zone_in_minority_class_is_specific(no_sources):
    feats = _two_class_features() + [_recinto(-1.600, 42.80, -1.595, 42.81, "Arcillosa")]
    zone = {"zoneId": "z3", "zoneVersion": "v1", "geometry": _square(-1.585, 42.805, -1.581, 42.815)}
    with patch.object(IdenaProvider, "features_for_bbox", AsyncMock(return_value=feats)):
        r = await zonal.resolve_zone_soil("acme", "p1", PARCEL_SUMMARY, zone)
    assert (r["provider"], r["fidelity"]) == ("idena", "zone_specific")
    assert (r["horizon"]["sand"], r["horizon"]["clay"]) == (65.0, 10.0)  # Franco arenosa
    assert r["horizon"]["usdaTextureClass"] == "sandy-loam"
    assert r["horizon"]["organicCarbon"] == 1.2  # not in IDENA: parcel value


@pytest.mark.asyncio
async def test_idena_single_class_parcel_is_inherited(no_sources):
    feats = [_recinto(-1.61, 42.79, -1.57, 42.83, "Franca")]
    with patch.object(IdenaProvider, "features_for_bbox", AsyncMock(return_value=feats)):
        r = await zonal.resolve_zone_soil("acme", "p1", PARCEL_SUMMARY, ZONE_A)
    assert (r["provider"], r["fidelity"]) == ("soilgrids", "parcel_inherited")
    assert r["horizon"]["sand"] == 40.0


@pytest.mark.asyncio
async def test_idena_zone_inside_corner_class_is_specific(no_sources):
    # Parcel: mostly Franca, one corner Arcillosa that holds the whole zone.
    zone = {"zoneId": "z4", "zoneVersion": "v1", "geometry": _square(-1.6, 42.8, -1.5995, 42.8005)}
    feats = [
        _recinto(-1.60, 42.80, -1.599, 42.801, "Arcillosa"),
        _recinto(-1.599, 42.80, -1.58, 42.82, "Franca"),
        _recinto(-1.60, 42.801, -1.599, 42.82, "Franca"),
    ]
    with patch.object(IdenaProvider, "features_for_bbox", AsyncMock(return_value=feats)):
        r = await zonal.resolve_zone_soil("acme", "p1", PARCEL_SUMMARY, zone)
    assert (r["provider"], r["fidelity"]) == ("idena", "zone_specific")
    assert r["horizon"]["clay"] == 60.0


@pytest.mark.asyncio
async def test_lucas_point_inside_zone(no_sources):
    vals = {"sand": 30.0, "silt": 40.0, "clay": 30.0, "organic_carbon": 1.0, "ph": 8.0}
    with patch.object(zonal, "_lucas_in_zone", AsyncMock(return_value=vals)):
        r = await zonal.resolve_zone_soil("acme", "p1", PARCEL_SUMMARY, ZONE_A)
    assert (r["provider"], r["fidelity"]) == ("LUCAS", "zone_specific")
    assert r["horizon"]["ph"] == 8.0


@pytest.mark.asyncio
async def test_nothing_resolves_returns_parcel_values(no_sources):
    r = await zonal.resolve_zone_soil("acme", "p1", PARCEL_SUMMARY, ZONE_A)
    assert r["fidelity"] == "parcel_inherited" and r["provider"] == "soilgrids"
    h = r["horizon"]
    assert (h["sand"], h["silt"], h["clay"]) == (40.0, 40.0, 20.0)
    assert h["availableWaterCapacity"] == 0.13 and h["hydrologicGroup"] == "B"
    assert h["usdaTextureClass"] == "loam" and h["ph"] == 7.5
    assert set(h) == {
        "sand", "silt", "clay", "organicCarbon", "fieldCapacity", "wiltingPoint",
        "availableWaterCapacity", "ksatSaturated", "hydrologicGroup",
        "usdaTextureClass", "ph",
    }


@pytest.mark.asyncio
async def test_source_error_falls_through_and_is_flagged(no_sources):
    with patch.object(zonal, "_sampling_points_in_zone", AsyncMock(side_effect=RuntimeError("orion down"))):
        r = await zonal.resolve_zone_soil("acme", "p1", PARCEL_SUMMARY, ZONE_A)
    assert r["fidelity"] == "parcel_inherited"
    assert r["_degraded"] is True


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = v

    async def scan_iter(self, match=None):
        import fnmatch
        for k in list(self.store):
            if fnmatch.fnmatch(k, match):
                yield k

    async def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)


@pytest.mark.asyncio
async def test_second_call_same_version_is_served_from_cache(no_sources):
    redis = FakeRedis()
    with patch.object(zonal, "_cache_client", lambda: redis):
        first = await zonal.resolve_zone_soil_cached("acme", "p1", PARCEL_SUMMARY, ZONE_A)
        with patch.object(zonal, "resolve_zone_soil", AsyncMock(side_effect=AssertionError("called"))):
            second = await zonal.resolve_zone_soil_cached("acme", "p1", PARCEL_SUMMARY, ZONE_A)
    assert second == first
    assert any(k.startswith("soil:zonal:acme:p1:v1") for k in redis.store)


@pytest.mark.asyncio
async def test_degraded_result_is_not_cached(no_sources):
    redis = FakeRedis()
    with (
        patch.object(zonal, "_cache_client", lambda: redis),
        patch.object(zonal, "_sampling_points_in_zone", AsyncMock(side_effect=RuntimeError("x"))),
    ):
        r = await zonal.resolve_zone_soil_cached("acme", "p1", PARCEL_SUMMARY, ZONE_A)
    assert "_degraded" not in r and redis.store == {}


@pytest.mark.asyncio
async def test_invalidate_parcel_deletes_only_that_parcel():
    redis = FakeRedis()
    redis.store = {
        "soil:zonal:acme:p1:v1:z1:0-60": "{}",
        "soil:zonal:acme:p1:v2:z1:0-60": "{}",
        "soil:zonal:acme:p2:v1:z1:0-60": "{}",
    }
    await zonal.invalidate_parcel("acme", "urn:ngsi-ld:AgriParcel:p1", client=redis)
    assert list(redis.store) == ["soil:zonal:acme:p2:v1:z1:0-60"]


@pytest.mark.asyncio
async def test_invalidate_parcel_never_raises():
    bad = MagicMock()
    bad.scan_iter = MagicMock(side_effect=RuntimeError("redis down"))
    await zonal.invalidate_parcel("acme", "p1", client=bad)


def _cog(arr, x0, y0, res):
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import from_origin
    buf = io.BytesIO()
    with rasterio.open(buf, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype="float64", crs=CRS.from_epsg(4326), transform=from_origin(x0, y0, res, res)) as dst:
        dst.write(arr, 1)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_raster_zonal_mean_reads_cog_inside_zone():
    arr = np.full((20, 20), 50.0)
    arr[:, 10:] = 30.0  # east half 30
    data = _cog(arr, -1.60, 42.82, 0.001)  # covers lon -1.60..-1.58
    s3 = MagicMock()
    s3.get_object.side_effect = lambda **_: {"Body": io.BytesIO(data)}
    entities = [{
        "id": "urn:ngsi-ld:SoilDerivedRaster:1",
        "hasAgriParcel": {"object": "urn:ngsi-ld:AgriParcel:acme:p1"},
        "soilProperty": {"value": "clay"},
        "depthFrom": {"value": 0}, "depthTo": {"value": 60},
        "storageUri": {"value": "s3://bkt/p1/v1/soil-clay-0-60.tif"},
    }]
    orion = AsyncMock()
    orion.__aenter__.return_value = orion
    orion.query_entities.return_value = entities
    west = _square(-1.599, 42.801, -1.592, 42.818)
    with (
        patch.object(zonal, "OrionClient", return_value=orion),
        patch.object(zonal, "get_minio_client", return_value=s3),
    ):
        vals = await zonal._raster_values_in_zone("acme", "p1", west, (0, 60))
        none = await zonal._raster_values_in_zone("acme", "p1", _square(10, 10, 10.1, 10.1), (0, 60))
    assert vals is not None and vals["clay"] == pytest.approx(50.0)
    assert none is None
