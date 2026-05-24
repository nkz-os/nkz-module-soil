"""ESDB Raster Library v2 provider — samples COGs from MinIO at query point.

Reads catalog from soil_module.esdb_raster_index, then samples band values
from the matching COGs stored in MinIO.

COORDINATE CONVENTION (Phase 1–3):
The esdb_raster_loader stores raw raster-CRS coordinates (typically EPSG:3035)
in the bbox column, which is typed EPSG:4326. Downstream queries that use
ST_Contains(bbox, ST_MakePoint(lon, lat)) therefore expect lon/lat to be in
the raster's native CRS unit space, not in geographic degrees.

TODO(phase4): once esdb_raster_loader reprojects bbox to true EPSG:4326, add
rio_transform("EPSG:4326", ds.crs, [lon], [lat]) here before sampling.
"""
from __future__ import annotations
import os
from urllib.parse import urlparse

import boto3
from rasterio.io import MemoryFile

from nkz_soil.providers.base import ProviderResult
from nkz_soil.storage.pg import get_pool

# Maps ESDB variable name → AgriSoilExtended NGSI-LD attribute name.
_VAR_MAP = {
    "CLAY": "clayContent",
    "SAND": "sandContent",
    "SILT": "siltContent",
    "OC": "organicCarbon",
    "PH": "ph",
}


class EsdbRasterProvider:
    name = "ESDB-Raster"
    priority = 18

    def __init__(self, variables: list[str] | None = None) -> None:
        self.variables = variables or list(_VAR_MAP.keys())

    async def fetch(
        self,
        *,
        lat: float,
        lon: float,
        geometry: dict | None = None,
    ) -> ProviderResult | None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT variable, depth_layer, storage_uri, crs
                FROM soil_module.esdb_raster_index
                WHERE variable = ANY($1::text[])
                  AND depth_layer IN ('TOP', 'ALL')
                  AND ST_Contains(bbox, ST_SetSRID(ST_MakePoint($2, $3), 4326))
                """,
                self.variables, lon, lat,
            )
        if not rows:
            return None

        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ["MINIO_ENDPOINT"],
            aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
            aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
        )
        attrs: dict[str, float] = {}
        for r in rows:
            uri = urlparse(r["storage_uri"])
            obj = s3.get_object(Bucket=uri.netloc, Key=uri.path.lstrip("/"))
            body = obj["Body"].read()
            with MemoryFile(body) as mem, mem.open() as ds:
                # Use lon/lat directly as raster-space coordinates (see module docstring).
                try:
                    val = next(ds.sample([(lon, lat)]))[0]
                except (StopIteration, IndexError):
                    continue
                attr = _VAR_MAP.get(r["variable"].upper())
                if attr and val is not None:
                    attrs[attr] = float(val)

        if not attrs:
            return None

        return ProviderResult(
            priority=self.priority,
            attributes=attrs,
            source_tag="ESDB-Raster-v2",
            license="JRC-ESDB-Raster-Attribution",
            entitlement_required="open",
        )

    async def health(self) -> dict:
        pool = await get_pool()
        async with pool.acquire() as conn:
            n = await conn.fetchval(
                "SELECT COUNT(*) FROM soil_module.esdb_raster_index"
            )
        return {"name": self.name, "status": "ok", "cataloged_rasters": n}
