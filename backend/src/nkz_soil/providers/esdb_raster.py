from __future__ import annotations
import os
from urllib.parse import urlparse

import boto3
from rasterio.io import MemoryFile
from rasterio.warp import transform as warp_transform

from nkz_soil.models.domain import SoilDataResult, Horizon
from nkz_soil.providers.base import geometry_intersects_bbox
from nkz_soil.storage.pg import get_pool

# ESDB variable -> Horizon field
_VAR_TO_HORIZON = {"CLAY": "clay", "SAND": "sand", "SILT": "silt",
                   "OC": "organic_carbon", "PH": "ph"}
_TOPSOIL = {(0, 5), (5, 15), (15, 30)}


def _centroid(geometry: dict) -> tuple[float, float]:
    if geometry.get("type") == "Point":
        c = geometry["coordinates"]
        return c[0], c[1]
    if geometry.get("type") == "Polygon":
        ring = geometry["coordinates"][0]
        return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
    return 0.0, 0.0


def _sample(ds, lon: float, lat: float) -> float | None:
    """Reproject (lon,lat) into the raster CRS, sample, return None on NoData/oob."""
    xs, ys = warp_transform("EPSG:4326", ds.crs, [lon], [lat])
    try:
        val = next(ds.sample([(xs[0], ys[0])]))[0]
    except (StopIteration, IndexError):
        return None
    if val is None:
        return None
    if ds.nodata is not None and float(val) == float(ds.nodata):
        return None
    if float(val) <= -3.0e38:  # Float32 sentinel guard when nodata undeclared
        return None
    return float(val)


class EsdbRasterProvider:
    name = "ESDB-Raster"
    priority = 18

    def __init__(self, variables: list[str] | None = None) -> None:
        self.variables = variables or list(_VAR_TO_HORIZON.keys())

    def covers(self, geometry: dict) -> bool:
        return geometry_intersects_bbox(geometry, (-25, 34, 45, 72))

    async def fetch(self, geometry: dict, properties, depths) -> SoilDataResult | None:
        lon, lat = _centroid(geometry)
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT variable, storage_uri
                FROM soil_module.esdb_raster_index
                WHERE variable = ANY($1::text[])
                  AND depth_layer IN ('TOP', 'ALL')
                  AND ST_Contains(bbox, ST_SetSRID(ST_MakePoint($2, $3), 4326))
                """,
                self.variables, lon, lat,
            )
        if not rows:
            return None

        s3 = boto3.client("s3", endpoint_url=os.environ["MINIO_ENDPOINT"],
                          aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
                          aws_secret_access_key=os.environ["MINIO_SECRET_KEY"])
        topvals: dict[str, float] = {}
        for r in rows:
            field = _VAR_TO_HORIZON.get(r["variable"].upper())
            if not field:
                continue
            uri = urlparse(r["storage_uri"])
            body = s3.get_object(Bucket=uri.netloc, Key=uri.path.lstrip("/"))["Body"].read()
            with MemoryFile(body) as mem, mem.open() as ds:
                v = _sample(ds, lon, lat)
            if v is not None:
                topvals[field] = round(v, 3)
        if not topvals:
            return None

        horizons = [Horizon(depth_from=d.depth_from, depth_to=d.depth_to, **topvals)
                    for d in depths if (d.depth_from, d.depth_to) in _TOPSOIL]
        if not horizons:
            return None
        return SoilDataResult(
            provider=self.name, horizons=horizons, uncertainty=0.3, geometry=geometry,
            attribution="Panagos et al. 2022 (ESDBv2 Raster Library)",
            license="JRC-ESDB-Raster-Attribution", redistributable=True, priority=self.priority,
        )

    async def health(self) -> dict:
        pool = await get_pool()
        async with pool.acquire() as conn:
            n = await conn.fetchval("SELECT COUNT(*) FROM soil_module.esdb_raster_index")
        return {"name": self.name, "status": "ok", "cataloged_rasters": n}
