"""ESDB raster cataloger: MinIO objects → soil_module.esdb_raster_index rows."""
from __future__ import annotations
import asyncpg
import os

from nkz_soil.ingest.esdb_raster_loader import catalog_esdb_rasters
from nkz_soil.storage import pg as pg_module

from .conftest import _run


def test_catalogs_only_matching_rasters(pg_dsn, minio_with_objects):
    pg_module._POOL = None
    n = _run(catalog_esdb_rasters(bucket="nekazari-soil-raw", prefix="esdb/"))
    assert n == 3

    async def _rows():
        conn = await asyncpg.connect(os.environ["SOIL_PG_DSN"])
        try:
            return await conn.fetch(
                "SELECT variable, depth_layer FROM soil_module.esdb_raster_index ORDER BY variable, depth_layer"
            )
        finally:
            await conn.close()
    rows = _run(_rows())
    assert [(r["variable"], r["depth_layer"]) for r in rows] == [
        ("CLAY", "SUB"), ("CLAY", "TOP"), ("OC", "TOP"),
    ]
