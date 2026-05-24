"""Bulk-load LUCAS 2018 topsoil CSV into soil_module.lucas_topsoil_2018.

Idempotent: ON CONFLICT (point_id) DO UPDATE.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from nkz_soil.storage.pg import get_pool

# Mapping LUCAS CSV column → DB column.
_COLS = {
    "POINTID": "point_id",
    "NUTS_0": "country_code",
    "NUTS_1": "nuts1",
    "NUTS_2": "nuts2",
    "ELEV": "elevation_m",
    "LC0_Desc": "land_cover",
    "LU1_Desc": "land_use",
    "pH_H2O": "ph_h2o",
    "pH_CaCl2": "ph_cacl2",
    "EC": "ec_ds_m",
    "OC": "oc_g_kg",
    "CaCO3": "caco3_g_kg",
    "P": "p_mg_kg",
    "N": "n_g_kg",
    "K": "k_mg_kg",
    "Coarse": "coarse_pct",
    "Sand": "sand_pct",
    "Silt": "silt_pct",
    "Clay": "clay_pct",
}

_UPSERT_SQL = """
INSERT INTO soil_module.lucas_topsoil_2018 (
    point_id, country_code, nuts1, nuts2, elevation_m, land_cover, land_use,
    ph_h2o, ph_cacl2, ec_ds_m, oc_g_kg, caco3_g_kg, p_mg_kg, n_g_kg, k_mg_kg,
    coarse_pct, sand_pct, silt_pct, clay_pct, geom
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
    $16, $17, $18, $19, ST_SetSRID(ST_MakePoint($20, $21), 4326)
)
ON CONFLICT (point_id) DO UPDATE SET
    ph_h2o = EXCLUDED.ph_h2o, ph_cacl2 = EXCLUDED.ph_cacl2,
    ec_ds_m = EXCLUDED.ec_ds_m, oc_g_kg = EXCLUDED.oc_g_kg,
    caco3_g_kg = EXCLUDED.caco3_g_kg, p_mg_kg = EXCLUDED.p_mg_kg,
    n_g_kg = EXCLUDED.n_g_kg, k_mg_kg = EXCLUDED.k_mg_kg,
    coarse_pct = EXCLUDED.coarse_pct, sand_pct = EXCLUDED.sand_pct,
    silt_pct = EXCLUDED.silt_pct, clay_pct = EXCLUDED.clay_pct,
    geom = EXCLUDED.geom, ingested_at = NOW();
"""


async def load_lucas_topsoil(csv_path: Path) -> int:
    """Load LUCAS topsoil CSV into PostGIS. Returns number of rows ingested."""
    df = pd.read_csv(csv_path)
    pool = await get_pool()
    n = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for _, row in df.iterrows():
                await conn.execute(
                    _UPSERT_SQL,
                    int(row["POINTID"]),
                    str(row["NUTS_0"]),
                    str(row.get("NUTS_1") or "") or None,
                    str(row.get("NUTS_2") or "") or None,
                    float(row.get("ELEV") or 0) or None,
                    str(row.get("LC0_Desc") or "") or None,
                    str(row.get("LU1_Desc") or "") or None,
                    *(_safe_float(row, c) for c in ["pH_H2O", "pH_CaCl2", "EC", "OC", "CaCO3", "P", "N", "K", "Coarse", "Sand", "Silt", "Clay"]),
                    float(row["TH_LONG"]),
                    float(row["TH_LAT"]),
                )
                n += 1
    return n


def _safe_float(row, col):
    v = row.get(col)
    try:
        return float(v) if pd.notna(v) else None
    except (TypeError, ValueError):
        return None
