"""Outage vs empty answer, per-zone isolation and per-request memoisation."""
import io
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import numpy as np
import pytest
from nkz_soil.providers.idena import IdenaProvider
from nkz_soil.services import zonal
from test_zonal_service import PARCEL_GEOM, PARCEL_SUMMARY, FakeRedis, _cog, _square


def _zone(i, version="v1"):
    x = -1.60 + 0.0005 * i
    return {"zoneId": f"z{i}", "zoneVersion": version, "geometry": _square(x, 42.80, x + 0.0004, 42.81)}


@pytest.fixture
def quiet():
    with (
        patch.object(zonal, "_sampling_points_in_zone", AsyncMock(return_value=[])),
        patch.object(zonal, "_raster_values_in_zone", AsyncMock(return_value=None)),
        patch.object(zonal, "_lucas_in_zone", AsyncMock(return_value=None)),
    ):
        yield


def _wfs(status, features=None):
    def handler(request):
        return httpx.Response(status, json={"features": features or []})

    real = httpx.AsyncClient
    return patch("nkz_soil.providers.idena.httpx.AsyncClient",
                 lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


@pytest.mark.asyncio
async def test_strict_wfs_raises_on_non_200_but_empty_200_is_fine():
    with _wfs(503):
        with pytest.raises(RuntimeError):
            await IdenaProvider().features_for_bbox(0, 0, 1, 1, strict=True)
        assert await IdenaProvider().features_for_bbox(0, 0, 1, 1) == []  # non-strict unchanged
    with _wfs(200, []):
        assert await IdenaProvider().features_for_bbox(0, 0, 1, 1, strict=True) == []


@pytest.mark.asyncio
async def test_idena_outage_is_not_cached_but_empty_answer_is(quiet):
    redis = FakeRedis()
    zone = _zone(0)
    with patch.object(zonal, "_cache_client", lambda: redis):
        with _wfs(503):
            r = await zonal.resolve_zone_soil_cached("acme", "p1", PARCEL_SUMMARY, zone)
        assert r["fidelity"] == "parcel_inherited" and redis.store == {}
        with _wfs(200, []):
            r = await zonal.resolve_zone_soil_cached("acme", "p1", PARCEL_SUMMARY, zone)
        assert r["fidelity"] == "parcel_inherited" and len(redis.store) == 1


@pytest.mark.asyncio
async def test_failing_zone_returns_parcel_values_with_warning(quiet, caplog):
    pts = [{"horizons": {"type": "Property", "value": [
        {"depthFrom": 0, "depthTo": 30, "sand": 60, "silt": 25, "clay": 15, "organicCarbon": 1}]}}]
    with (
        patch.object(zonal, "_sampling_points_in_zone", AsyncMock(return_value=pts)),
        patch.object(zonal, "_with_pedotransfer", side_effect=RuntimeError("boom")),
        patch.object(IdenaProvider, "features_for_bbox", AsyncMock(return_value=[])),
        caplog.at_level("WARNING"),
    ):
        r = await zonal.resolve_zone_soil("acme", "p1", PARCEL_SUMMARY, _zone(3))
    assert (r["fidelity"], r["provider"]) == ("parcel_inherited", "soilgrids")
    assert r["horizon"]["sand"] == 40.0 and r["_degraded"] is True
    assert any(getattr(rec, "zone", None) == "z3" for rec in caplog.records)


@pytest.mark.asyncio
async def test_unusable_parcel_summary_still_does_not_raise(quiet):
    with patch.object(IdenaProvider, "features_for_bbox", AsyncMock(return_value=[])):
        r = await zonal.resolve_zone_soil("acme", "p1", {"horizons": [{"depthFrom": "x"}]}, _zone(0))
    assert r["fidelity"] == "parcel_inherited"


@pytest.mark.asyncio
async def test_twenty_zones_one_wfs_call(quiet):
    feats = [{"type": "Feature", "geometry": PARCEL_GEOM, "properties": {"CLASIF_HS1": "Franca"}}]
    m = AsyncMock(return_value=feats)
    ctx: dict = {}
    with patch.object(IdenaProvider, "features_for_bbox", m):
        for i in range(20):
            await zonal.resolve_zone_soil("acme", "p1", PARCEL_SUMMARY, _zone(i), ctx=ctx)
    assert m.await_count == 1
    assert m.await_args.kwargs["strict"] is True


@pytest.mark.asyncio
async def test_twenty_zones_one_download_per_raster_and_one_entity_query():
    arr = np.full((20, 20), 50.0)
    data = _cog(arr, -1.60, 42.82, 0.001)
    s3 = MagicMock()
    s3.get_object.side_effect = lambda **_: {"Body": io.BytesIO(data)}
    entities = [
        {"hasAgriParcel": {"object": "urn:ngsi-ld:AgriParcel:acme:p1"}, "soilProperty": {"value": prop},
         "depthFrom": {"value": 0}, "depthTo": {"value": 60},
         "storageUri": {"value": f"s3://b/p1/{prop}.tif"}}
        for prop in ("sand", "clay")
    ]
    orion = AsyncMock()
    orion.__aenter__.return_value = orion
    orion.query_entities.return_value = entities
    ctx: dict = {}
    with (
        patch.object(zonal, "OrionClient", return_value=orion),
        patch.object(zonal, "get_minio_client", return_value=s3),
    ):
        for i in range(20):
            v = await zonal._raster_values_in_zone("acme", "p1", _zone(i)["geometry"], (0, 60), ctx)
            assert v["sand"] == pytest.approx(50.0)
    assert s3.get_object.call_count == 2
    assert orion.query_entities.await_count == 1
