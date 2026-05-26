"""Catalog JRC LUCAS topsoil texture EU23 rasters (private MinIO) into
soil_module.lucas_texture_raster_index.

Only the *_eu23 products are catalogued (the official EU coverage mask); the
wider 'Extra' gap-filled variants are intentionally skipped. License is
NO-redistribution: this catalog only points at the rasters; values are served
solely as derived/aggregated outputs by LucasTextureRasterProvider.
"""
from __future__ import annotations
import os
from pathlib import PurePosixPath

import boto3
from rasterio.io import MemoryFile
from rasterio.warp import transform_bounds

from nkz_soil.storage.pg import get_pool

_TARGET_CRS = "EPSG:4326"

# Exact EU23 filenames -> catalog variable.
_FILENAME_TO_VAR = {
    "clay_eu23.tif": "CLAY",
    "sand_eu23.tif": "SAND",
    "silt_eu23.tif": "SILT",
    "bulk_density_eu23.tif": "BULK_DENSITY",
    "awc_eu23.tif": "AWC",
    "coarse_frag_eu23.tif": "COARSE_FRAGMENTS",
    "textureusda_eu23.tif": "USDA_TEXTURE",
}

_UPSERT = """
INSERT INTO soil_module.lucas_texture_raster_index
    (variable, storage_uri, bbox, crs, resolution_m, nodata)
VALUES ($1, $2, ST_GeomFromText($3, 4326), $4, $5, $6)
ON CONFLICT (variable) DO UPDATE SET
    storage_uri = EXCLUDED.storage_uri, bbox = EXCLUDED.bbox, crs = EXCLUDED.crs,
    resolution_m = EXCLUDED.resolution_m, nodata = EXCLUDED.nodata, cataloged_at = NOW();
"""


def _variable_for(filename: str) -> str | None:
    return _FILENAME_TO_VAR.get(filename.lower())


def _bbox_wkt(w: float, s: float, e: float, n: float) -> str:
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


async def catalog_lucas_texture(
    bucket: str = "nekazari-soil-restricted",
    prefix: str = "lucas-texture/",
    endpoint: str | None = None, key: str | None = None, secret: str | None = None,
) -> int:
    """List EU23 texture rasters in MinIO, reproject bounds to 4326, upsert catalog rows."""
    endpoint = endpoint or os.environ["MINIO_ENDPOINT"]
    key = key or os.environ["MINIO_ACCESS_KEY"]
    secret = secret or os.environ["MINIO_SECRET_KEY"]
    s3 = boto3.client("s3", endpoint_url=endpoint,
                      aws_access_key_id=key, aws_secret_access_key=secret)

    cataloged = 0
    pool = await get_pool()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            name = PurePosixPath(obj["Key"]).name
            variable = _variable_for(name)
            if not variable:
                continue
            storage_uri = f"s3://{bucket}/{obj['Key']}"
            body = s3.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
            with MemoryFile(body) as mem, mem.open() as ds:
                src_crs = str(ds.crs) if ds.crs else "EPSG:3035"
                b = ds.bounds
                w, s, e, n = transform_bounds(src_crs, _TARGET_CRS,
                                              b.left, b.bottom, b.right, b.top, densify_pts=21)
                wkt = _bbox_wkt(w, s, e, n)
                res = int(round(abs(ds.transform[0])))
                nodata = float(ds.nodata) if ds.nodata is not None else None
            async with pool.acquire() as conn:
                await conn.execute(_UPSERT, variable, storage_uri, wkt, src_crs, res, nodata)
            cataloged += 1
    return cataloged
