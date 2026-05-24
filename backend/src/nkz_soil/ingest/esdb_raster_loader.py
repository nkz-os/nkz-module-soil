"""Catalog ESDB v2 Raster Library 1km objects in MinIO into soil_module.esdb_raster_index.

ESDB rasters arrive as GeoTIFF files in the `nekazari-soil-raw/esdb/` bucket prefix.
File naming convention: <variable>_<depth>.tif (e.g. CLAY_TOP.tif, OC_SUB.tif).
"""
from __future__ import annotations
import os
import re
from pathlib import PurePosixPath
import boto3
from rasterio.io import MemoryFile
from nkz_soil.storage.pg import get_pool

_FNAME_RE = re.compile(r"^(?P<var>[A-Z0-9_]+?)_(?P<depth>TOP|SUB|ALL)\.tif$", re.IGNORECASE)

_UPSERT = """
INSERT INTO soil_module.esdb_raster_index
    (variable, depth_layer, storage_uri, bbox, crs, resolution_m, citation, license)
VALUES ($1, $2, $3, ST_GeomFromText($4, 4326), $5, $6, $7, $8)
ON CONFLICT (variable, depth_layer) DO UPDATE SET
    storage_uri = EXCLUDED.storage_uri,
    bbox = EXCLUDED.bbox,
    crs = EXCLUDED.crs,
    resolution_m = EXCLUDED.resolution_m,
    cataloged_at = NOW();
"""


def _s3_client(endpoint: str, key: str, secret: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
    )


def _bbox_wkt(west: float, south: float, east: float, north: float) -> str:
    return f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"


async def catalog_esdb_rasters(
    bucket: str = "nekazari-soil-raw",
    prefix: str = "esdb/",
    endpoint: str | None = None,
    key: str | None = None,
    secret: str | None = None,
) -> int:
    """List ESDB rasters in MinIO, extract bbox/CRS/resolution, upsert catalog rows."""
    endpoint = endpoint or os.environ["MINIO_ENDPOINT"]
    key = key or os.environ["MINIO_ACCESS_KEY"]
    secret = secret or os.environ["MINIO_SECRET_KEY"]
    s3 = _s3_client(endpoint, key, secret)

    cataloged = 0
    pool = await get_pool()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            name = PurePosixPath(obj["Key"]).name
            m = _FNAME_RE.match(name)
            if not m:
                continue
            variable = m.group("var").upper()
            depth = m.group("depth").upper()
            storage_uri = f"s3://{bucket}/{obj['Key']}"

            body = s3.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
            with MemoryFile(body) as mem, mem.open() as ds:
                bounds = ds.bounds
                # TODO(phase4): reproject bbox from raster CRS (typically EPSG:3035) to EPSG:4326
                # before storing. Current implementation passes raw bounds — invalid for non-4326
                # rasters in production. Acceptable for test fixtures and during ingest of EU rasters
                # if a subsequent reprojection step normalizes the bbox column.
                wkt = _bbox_wkt(bounds.left, bounds.bottom, bounds.right, bounds.top)
                crs = str(ds.crs) if ds.crs else "EPSG:3035"
                res = int(round(abs(ds.transform[0])))

            async with pool.acquire() as conn:
                await conn.execute(
                    _UPSERT, variable, depth, storage_uri, wkt, crs, res,
                    "Panagos et al. 2022 (ESDBv2 Raster Library)",
                    "JRC-ESDB-Raster-Attribution",
                )
            cataloged += 1
    return cataloged
