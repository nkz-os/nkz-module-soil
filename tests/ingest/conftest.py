"""Shared pytest fixtures and helpers for ingest tests."""
from __future__ import annotations
import asyncio
import os
from pathlib import Path

import asyncpg
import boto3
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from testcontainers.minio import MinioContainer
from testcontainers.postgres import PostgresContainer

from nkz_soil.storage import pg as pg_module


# ---------------------------------------------------------------------------
# Helper — run a coroutine in a fresh event loop
# ---------------------------------------------------------------------------

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Postgres fixture — PostGIS container with migrations 001-004 applied
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_dsn():
    with PostgresContainer("postgis/postgis:16-3.4") as pg:
        dsn = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        os.environ["SOIL_PG_DSN"] = dsn
        pg_module._POOL = None  # ensure fresh pool per test module

        async def _migrate():
            conn = await asyncpg.connect(dsn)
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
                root = Path(__file__).resolve().parents[2] / "backend" / "migrations"
                # Apply the full migration set in order so the test schema matches
                # production (e.g. migration 006 realigns the aux tables).
                for m in sorted(root.glob("[0-9][0-9][0-9]_*.sql")):
                    await conn.execute(m.read_text())
            finally:
                await conn.close()

        asyncio.new_event_loop().run_until_complete(_migrate())
        yield dsn
        # Pool is loop-bound; container is torn down anyway — just null the ref.
        pg_module._POOL = None


# ---------------------------------------------------------------------------
# MinIO fixture — synthetic GeoTIFFs uploaded to a local MinioContainer
# ---------------------------------------------------------------------------

def _make_geotiff() -> bytes:
    """Synthetic 10x10 GeoTIFF, all values=42, EPSG:3035, origin (2000000, 3000000), 1km res."""
    data = np.full((10, 10), 42, dtype="float32")
    with rasterio.io.MemoryFile() as mem:
        with mem.open(
            driver="GTiff", height=10, width=10, count=1, dtype="float32",
            crs="EPSG:3035", transform=from_origin(2000000, 3000000, 1000, 1000),
        ) as ds:
            ds.write(data, 1)
        return mem.read()


@pytest.fixture(scope="module")
def minio_with_objects():
    with MinioContainer() as mc:
        endpoint = f"http://{mc.get_container_host_ip()}:{mc.get_exposed_port(9000)}"
        os.environ.update({
            "MINIO_ENDPOINT": endpoint,
            "MINIO_ACCESS_KEY": mc.access_key,
            "MINIO_SECRET_KEY": mc.secret_key,
        })
        s3 = boto3.client(
            "s3", endpoint_url=endpoint,
            aws_access_key_id=mc.access_key, aws_secret_access_key=mc.secret_key,
        )
        s3.create_bucket(Bucket="nekazari-soil-raw")
        tif = _make_geotiff()
        s3.put_object(Bucket="nekazari-soil-raw", Key="esdb/CLAY_TOP.tif", Body=tif)
        s3.put_object(Bucket="nekazari-soil-raw", Key="esdb/CLAY_SUB.tif", Body=tif)
        s3.put_object(Bucket="nekazari-soil-raw", Key="esdb/OC_TOP.tif", Body=tif)
        s3.put_object(Bucket="nekazari-soil-raw", Key="esdb/README.txt", Body=b"ignored")
        yield endpoint
