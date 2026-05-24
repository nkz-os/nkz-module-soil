"""LUCAS provider — PostGIS KNN query against soil_module.lucas_topsoil_2018.

Replaces remote CSV download. Returns inverse-distance-weighted average of the
k nearest points within `buffer_km`. Per-license, raw point coordinates are
NEVER returned to consumers — only aggregated values per query location.
"""
from __future__ import annotations

from nkz_soil.providers.base import ProviderResult, geometry_intersects_bbox
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

# Maps NGSI-LD / SDM attribute names to DB column names.
_ATTR_MAP = {
    "clayContent":            "clay_pct",
    "sandContent":            "sand_pct",
    "siltContent":            "silt_pct",
    "organicCarbon":          "oc_g_kg",
    "ph":                     "ph_h2o",
    "electricalConductivity": "ec_ds_m",
    "calciumCarbonate":       "caco3_g_kg",
    "phosphorus":             "p_mg_kg",
    "nitrogen":               "n_g_kg",
    "potassium":              "k_mg_kg",
    "coarseFragments":        "coarse_pct",
}


class LucasProvider:
    name = "LUCAS"
    priority = 25

    def __init__(self, buffer_km: float = 5.0, k: int = 3) -> None:
        self.buffer_km = buffer_km
        self.k = k

    def covers(self, geometry: dict) -> bool:
        """PostGIS decides actual coverage at query time; report EU+surrounding as covered."""
        return geometry_intersects_bbox(geometry, (-25, 34, 45, 72))

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
                _KNN_SQL, lon, lat, self.buffer_km * 1000, self.k
            )
        if not rows:
            return None

        # Inverse-distance weighting; clamp minimum distance to 1 m to avoid div-by-zero.
        weights = [1.0 / max(float(r["dist_m"]), 1.0) for r in rows]
        attrs: dict[str, float] = {}
        for ngsi_name, db_col in _ATTR_MAP.items():
            valid = [(r[db_col], w) for r, w in zip(rows, weights) if r[db_col] is not None]
            if not valid:
                continue
            num = sum(v * w for v, w in valid)
            denom = sum(w for _, w in valid)
            attrs[ngsi_name] = round(num / denom, 3)

        return ProviderResult(
            priority=self.priority,
            attributes=attrs,
            source_tag="LUCAS-2018",
            license="JRC-LUCAS-2018",
            entitlement_required="open",
            observed_at="2018-01-01T00:00:00Z",
        )

    async def health(self) -> dict:
        pool = await get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM soil_module.lucas_topsoil_2018"
            )
        return {"name": self.name, "status": "ok", "points": count}
