"""LUCAS provider — PostGIS KNN query against soil_module.lucas_topsoil_2018.

Replaces remote CSV download. Returns inverse-distance-weighted average of the
k nearest points within `buffer_km`. Per-license, raw point coordinates are
NEVER returned to consumers — only aggregated values per query location.
"""
from __future__ import annotations

from nkz_soil.models.domain import SoilDataResult, Horizon
from nkz_soil.providers.base import geometry_intersects_bbox
from nkz_soil.storage.pg import get_pool

_KNN_SQL = """
SELECT
    clay_pct, sand_pct, silt_pct, oc_g_kg, ph_h2o, ec_ds_m, caco3_g_kg,
    p_mg_kg, n_g_kg, k_mg_kg, coarse_pct,
    ST_Distance(
        geom::geography,
        ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography
    ) AS dist_m
FROM soil_module.lucas_topsoil_2018
WHERE ST_DWithin(
    geom::geography,
    ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography,
    $3
)
ORDER BY geom <-> ST_SetSRID(ST_MakePoint($1, $2), 4326)
LIMIT $4;
"""

# DB column -> Horizon field (None = not mapped to a horizon attribute)
_COL_TO_HORIZON = {
    "clay_pct": "clay", "sand_pct": "sand", "silt_pct": "silt",
    "oc_g_kg": "organic_carbon", "ph_h2o": "ph", "ec_ds_m": None,
    "caco3_g_kg": None, "p_mg_kg": None, "n_g_kg": None, "k_mg_kg": None,
    "coarse_pct": "coarse_fragments",
}
_TOPSOIL_DEPTHS = {(0, 5), (5, 15), (15, 30)}


def _centroid(geometry: dict) -> tuple[float, float]:
    if geometry.get("type") == "Point":
        c = geometry["coordinates"]
        return c[0], c[1]
    if geometry.get("type") == "Polygon":
        ring = geometry["coordinates"][0]
        return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
    return 0.0, 0.0


class LucasProvider:
    name = "LUCAS"
    priority = 25

    def __init__(self, buffer_km: float = 5.0, k: int = 3) -> None:
        self.buffer_km = buffer_km
        self.k = k

    def covers(self, geometry: dict) -> bool:
        return geometry_intersects_bbox(geometry, (-25, 34, 45, 72))

    async def fetch(self, geometry: dict, properties, depths) -> SoilDataResult | None:
        lon, lat = _centroid(geometry)
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(_KNN_SQL, lon, lat, self.buffer_km * 1000, self.k)
        if not rows:
            return None

        weights = [1.0 / max(float(r["dist_m"]), 1.0) for r in rows]
        topvals: dict[str, float] = {}
        for col, field in _COL_TO_HORIZON.items():
            if field is None:
                continue
            valid = [(r[col], w) for r, w in zip(rows, weights) if r[col] is not None]
            if not valid:
                continue
            topvals[field] = round(sum(v * w for v, w in valid) / sum(w for _, w in valid), 3)

        # LUCAS stores organic carbon in g/kg, but the canonical organicCarbon unit
        # is percent (capabilities.yaml P1) and Saxton-Rawls expects %. Convert.
        if "organic_carbon" in topvals:
            topvals["organic_carbon"] = round(topvals["organic_carbon"] / 10.0, 3)

        horizons = [
            Horizon(depth_from=d.depth_from, depth_to=d.depth_to, **topvals)
            for d in depths if (d.depth_from, d.depth_to) in _TOPSOIL_DEPTHS
        ]
        if not horizons:
            return None

        return SoilDataResult(
            provider=self.name, horizons=horizons, uncertainty=0.2, geometry=geometry,
            attribution="JRC LUCAS 2018 Topsoil", license="JRC-LUCAS-2018",
            redistributable=True, priority=self.priority,
        )

    async def health(self) -> dict:
        pool = await get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM soil_module.lucas_topsoil_2018")
        return {"name": self.name, "status": "ok", "points": count}
