"""LUCAS topsoil texture raster provider (JRC, Ballabio et al. 2016).

License is NO-redistribution: this provider returns raw fractions tagged
redistributable=False, so the worker's suppression boundary withholds them
from the served entity and emits only derived products + USDA class.

Values are PARCEL-AGGREGATED (mean over interior sample points), never a single
arbitrary-point read, to avoid raster reconstruction by sampling.
"""
from __future__ import annotations
import os
from urllib.parse import urlparse

import boto3
from rasterio.io import MemoryFile
from rasterio.warp import transform as warp_transform
from shapely.geometry import Point, shape

from nkz_soil.models.domain import SoilDataResult, Horizon
from nkz_soil.providers.base import geometry_intersects_bbox
from nkz_soil.storage.pg import get_pool

# Catalog variable -> Horizon field. USDA_TEXTURE is catalogued for QC but not
# emitted here: the class is self-computed downstream from the aggregated fractions.
_VAR_TO_HORIZON = {
    "CLAY": "clay", "SAND": "sand", "SILT": "silt",
    "BULK_DENSITY": "bulk_density", "COARSE_FRAGMENTS": "coarse_fragments",
}
_TOPSOIL = {(0, 5), (5, 15), (15, 30)}


def _sample_points(geometry: dict, n: int = 9) -> list[tuple[float, float]]:
    """Centroid + up to n-1 interior grid points clipped to the polygon."""
    if geometry.get("type") == "Point":
        c = geometry["coordinates"]
        return [(c[0], c[1])]
    if geometry.get("type") != "Polygon":
        return []
    geom = shape(geometry)
    c = geom.centroid
    pts = [(c.x, c.y)]
    minx, miny, maxx, maxy = geom.bounds
    side = max(1, int(n ** 0.5))
    for i in range(1, side + 1):
        for j in range(1, side + 1):
            x = minx + (maxx - minx) * i / (side + 1)
            y = miny + (maxy - miny) * j / (side + 1)
            if geom.contains(Point(x, y)):
                pts.append((x, y))
    return pts[:n]


def _read_value(ds, lon: float, lat: float) -> float | None:
    xs, ys = warp_transform("EPSG:4326", ds.crs, [lon], [lat])
    try:
        val = next(ds.sample([(xs[0], ys[0])]))[0]
    except (StopIteration, IndexError):
        return None
    if val is None:
        return None
    if ds.nodata is not None and float(val) == float(ds.nodata):
        return None
    if float(val) <= -3.0e38:
        return None
    return float(val)


class LucasTextureRasterProvider:
    name = "LUCAS-Texture"
    priority = 22

    def covers(self, geometry: dict) -> bool:
        return geometry_intersects_bbox(geometry, (-25, 34, 45, 72))

    async def fetch(self, geometry: dict, properties, depths) -> SoilDataResult | None:
        pts = _sample_points(geometry)
        if not pts:
            return None
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT variable, storage_uri
                FROM soil_module.lucas_texture_raster_index
                WHERE variable = ANY($1::text[])
                  AND ST_Contains(bbox, ST_SetSRID(ST_MakePoint($2, $3), 4326))
                """,
                list(_VAR_TO_HORIZON.keys()), pts[0][0], pts[0][1],
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
                vals = [v for v in (_read_value(ds, lon, lat) for lon, lat in pts) if v is not None]
            if vals:
                topvals[field] = round(sum(vals) / len(vals), 3)
        if not topvals:
            return None

        horizons = [Horizon(depth_from=d.depth_from, depth_to=d.depth_to, **topvals)
                    for d in depths if (d.depth_from, d.depth_to) in _TOPSOIL]
        if not horizons:
            return None
        return SoilDataResult(
            provider=self.name, horizons=horizons, uncertainty=0.2, geometry=geometry,
            attribution="Ballabio C., Panagos P., Montanarella L. (2016) Geoderma 261:110-123",
            license="JRC-ESDAC-NoRedistribution", redistributable=False, priority=self.priority,
        )

    async def health(self) -> dict:
        pool = await get_pool()
        async with pool.acquire() as conn:
            n = await conn.fetchval(
                "SELECT COUNT(*) FROM soil_module.lucas_texture_raster_index")
        return {"name": self.name, "status": "ok", "cataloged_rasters": n}
