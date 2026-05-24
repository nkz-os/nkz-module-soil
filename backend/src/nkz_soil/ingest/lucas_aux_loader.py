"""Loaders for LUCAS auxiliary datasets: bulk density, erosion, organic, texture."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from nkz_soil.storage.pg import get_pool


_BD_UPSERT = """
INSERT INTO soil_module.lucas_bulk_density_2018 (point_id, bd_fine_g_cm3, bd_total_g_cm3, coarse_frag_pct, geom)
VALUES ($1, $2, $3, $4, ST_SetSRID(ST_MakePoint($5, $6), 4326))
ON CONFLICT (point_id) DO UPDATE SET
    bd_fine_g_cm3 = EXCLUDED.bd_fine_g_cm3,
    bd_total_g_cm3 = EXCLUDED.bd_total_g_cm3,
    coarse_frag_pct = EXCLUDED.coarse_frag_pct,
    geom = EXCLUDED.geom;
"""

_EROSION_UPSERT = """
INSERT INTO soil_module.lucas_erosion_2018 (point_id, erosion_class, severity_score, geom)
VALUES ($1, $2, $3, ST_SetSRID(ST_MakePoint($4, $5), 4326))
ON CONFLICT (point_id) DO UPDATE SET
    erosion_class = EXCLUDED.erosion_class,
    severity_score = EXCLUDED.severity_score,
    geom = EXCLUDED.geom;
"""

_ORGANIC_UPSERT = """
INSERT INTO soil_module.lucas_organic_2018 (point_id, horizon_depth_cm, horizon_oc_g_kg, horizon_n_g_kg, geom)
VALUES ($1, $2, $3, $4, ST_SetSRID(ST_MakePoint($5, $6), 4326))
ON CONFLICT (point_id) DO UPDATE SET
    horizon_depth_cm = EXCLUDED.horizon_depth_cm,
    horizon_oc_g_kg = EXCLUDED.horizon_oc_g_kg,
    horizon_n_g_kg = EXCLUDED.horizon_n_g_kg,
    geom = EXCLUDED.geom;
"""

_TEXTURE_UPSERT = """
INSERT INTO soil_module.lucas_texture_all (point_id, survey_year, sand_pct, silt_pct, clay_pct, texture_class, geom)
VALUES ($1, $2, $3, $4, $5, $6, ST_SetSRID(ST_MakePoint($7, $8), 4326))
ON CONFLICT (point_id) DO UPDATE SET
    survey_year = EXCLUDED.survey_year,
    sand_pct = EXCLUDED.sand_pct,
    silt_pct = EXCLUDED.silt_pct,
    clay_pct = EXCLUDED.clay_pct,
    texture_class = EXCLUDED.texture_class,
    geom = EXCLUDED.geom;
"""


async def load_lucas_bulk_density(csv_path: Path) -> int:
    df = pd.read_csv(csv_path)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        for _, row in df.iterrows():
            await conn.execute(
                _BD_UPSERT,
                int(row["POINTID"]),
                _f(row, "BD_FINE"), _f(row, "BD_TOTAL"), _f(row, "COARSE_FRAG"),
                float(row["TH_LONG"]), float(row["TH_LAT"]),
            )
    return len(df)


async def load_lucas_erosion(csv_path: Path) -> int:
    df = pd.read_csv(csv_path)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        for _, row in df.iterrows():
            await conn.execute(
                _EROSION_UPSERT,
                int(row["POINTID"]),
                str(row.get("EROSION_CLASS") or "") or None,
                int(row["SEVERITY"]) if pd.notna(row.get("SEVERITY")) else None,
                float(row["TH_LONG"]), float(row["TH_LAT"]),
            )
    return len(df)


async def load_lucas_organic(csv_path: Path) -> int:
    df = pd.read_csv(csv_path)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        for _, row in df.iterrows():
            await conn.execute(
                _ORGANIC_UPSERT,
                int(row["POINTID"]),
                int(row["HORIZON_DEPTH"]) if pd.notna(row.get("HORIZON_DEPTH")) else None,
                _f(row, "HORIZON_OC"), _f(row, "HORIZON_N"),
                float(row["TH_LONG"]), float(row["TH_LAT"]),
            )
    return len(df)


async def load_lucas_texture(csv_path: Path) -> int:
    df = pd.read_csv(csv_path)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        for _, row in df.iterrows():
            await conn.execute(
                _TEXTURE_UPSERT,
                int(row["POINTID"]),
                int(row["SURVEY_YEAR"]),
                _f(row, "SAND"), _f(row, "SILT"), _f(row, "CLAY"),
                str(row.get("TEXTURE_CLASS") or "") or None,
                float(row["TH_LONG"]), float(row["TH_LAT"]),
            )
    return len(df)


def _f(row, col):
    v = row.get(col)
    try:
        return float(v) if pd.notna(v) else None
    except (TypeError, ValueError):
        return None
