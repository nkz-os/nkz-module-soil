"""ESDB-raster provider samples a COG at a query point, returning SoilDataResult."""
from __future__ import annotations
import pytest

from nkz_soil.ingest.esdb_raster_loader import catalog_esdb_rasters
from nkz_soil.providers.esdb_raster import EsdbRasterProvider
from nkz_soil.models.domain import SoilProperty, DepthInterval
from nkz_soil.storage import pg as pg_module

from .conftest import _run

_DEPTHS = [DepthInterval(0, 5)]
_PROPS = [SoilProperty.CLAY, SoilProperty.ORGANIC_CARBON]


@pytest.fixture(scope="module")
def cataloged(pg_dsn, minio_with_objects):
    pg_module._POOL = None
    _run(catalog_esdb_rasters(bucket="nekazari-soil-raw", prefix="esdb/"))
    return pg_dsn


def test_sample_returns_soildataresult_within_bbox(cataloged):
    pg_module._POOL = None

    async def go():
        pool = await pg_module.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT ST_X(ST_Centroid(bbox)) AS lon, ST_Y(ST_Centroid(bbox)) AS lat "
                "FROM soil_module.esdb_raster_index WHERE variable='CLAY' LIMIT 1")
        provider = EsdbRasterProvider(variables=["CLAY", "OC"])
        geom = {"type": "Point", "coordinates": [row["lon"], row["lat"]]}
        return await provider.fetch(geom, _PROPS, _DEPTHS)

    res = _run(go())
    assert res is not None
    assert res.provider == "ESDB-Raster"
    assert res.license == "JRC-ESDB-Raster-Attribution"
    assert res.redistributable is True
    assert res.priority == 18
    top = res.horizons[0]
    assert top.clay == 42.0
    assert top.organic_carbon == 42.0


def test_sample_returns_none_outside_all_bboxes(cataloged):
    pg_module._POOL = None
    provider = EsdbRasterProvider(variables=["CLAY", "OC"])
    geom = {"type": "Point", "coordinates": [0.0, 0.0]}
    res = _run(provider.fetch(geom, _PROPS, _DEPTHS))
    assert res is None
