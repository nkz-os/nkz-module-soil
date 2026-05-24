"""Loaders for LUCAS 2018 auxiliary datasets: bulk density, erosion, organic.

Column mappings reflect the published ESDAC CSV shape:
- BulkDensity_2018_final-2.csv: POINT_ID + 4 depth-interval bulk density columns
- LUCAS2018_EROSION.csv: POINT_ID + per-process presence flags (sheet/rill/gully/...)
- LUCAS2018_ORG.csv: POINT_ID + cultivated flag + 5 cardinal-direction depth probes

The CSVs carry no coordinates, so we resolve geom by joining against
soil_module.lucas_topsoil_2018 (pre-loaded). Points absent from the topsoil
table are skipped (they would violate the FK anyway).

Texture is not loaded here: the source file LUCAS_Text_All_10032025.csv is
not published in the 2018 SOIL bundle. Texture columns (sand/silt/clay) are
already available per-point on lucas_topsoil_2018.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from nkz_soil.storage.pg import get_pool


_BD_UPSERT = """
INSERT INTO soil_module.lucas_bulk_density_2018
    (point_id, bd_0_10_g_cm3, bd_10_20_g_cm3, bd_20_30_g_cm3, bd_0_20_g_cm3, geom)
SELECT $1, $2, $3, $4, $5, geom
FROM soil_module.lucas_topsoil_2018
WHERE point_id = $1
ON CONFLICT (point_id) DO UPDATE SET
    bd_0_10_g_cm3 = EXCLUDED.bd_0_10_g_cm3,
    bd_10_20_g_cm3 = EXCLUDED.bd_10_20_g_cm3,
    bd_20_30_g_cm3 = EXCLUDED.bd_20_30_g_cm3,
    bd_0_20_g_cm3 = EXCLUDED.bd_0_20_g_cm3,
    geom = EXCLUDED.geom;
"""

_EROSION_UPSERT = """
INSERT INTO soil_module.lucas_erosion_2018
    (point_id, signs_observed, sheet, rill, gully, mass, dep, wind, geom)
SELECT $1, $2, $3, $4, $5, $6, $7, $8, geom
FROM soil_module.lucas_topsoil_2018
WHERE point_id = $1
ON CONFLICT (point_id) DO UPDATE SET
    signs_observed = EXCLUDED.signs_observed,
    sheet = EXCLUDED.sheet,
    rill  = EXCLUDED.rill,
    gully = EXCLUDED.gully,
    mass  = EXCLUDED.mass,
    dep   = EXCLUDED.dep,
    wind  = EXCLUDED.wind,
    geom  = EXCLUDED.geom;
"""

_ORGANIC_UPSERT = """
INSERT INTO soil_module.lucas_organic_2018
    (point_id, cultivated, depth_mean_cm, reaches_40cm_any, sample_taken, geom)
SELECT $1, $2, $3, $4, $5, geom
FROM soil_module.lucas_topsoil_2018
WHERE point_id = $1
ON CONFLICT (point_id) DO UPDATE SET
    cultivated = EXCLUDED.cultivated,
    depth_mean_cm = EXCLUDED.depth_mean_cm,
    reaches_40cm_any = EXCLUDED.reaches_40cm_any,
    sample_taken = EXCLUDED.sample_taken,
    geom = EXCLUDED.geom;
"""


async def load_lucas_bulk_density(csv_path: Path) -> int:
    df = pd.read_csv(csv_path)
    pool = await get_pool()
    inserted = 0
    async with pool.acquire() as conn, conn.transaction():
        for _, row in df.iterrows():
            result = await conn.execute(
                _BD_UPSERT,
                int(row["POINT_ID"]),
                _f(row, "BD 0-10"),
                _f(row, "BD 10-20"),
                _f(row, "BD 20-30"),
                _f(row, "BD 0-20"),
            )
            if result.endswith(" 1"):
                inserted += 1
    return inserted


async def load_lucas_erosion(csv_path: Path) -> int:
    df = pd.read_csv(csv_path)
    pool = await get_pool()
    inserted = 0
    async with pool.acquire() as conn, conn.transaction():
        for _, row in df.iterrows():
            result = await conn.execute(
                _EROSION_UPSERT,
                int(row["POINT_ID"]),
                _i(row, "SURVEY_EROSION_SIGNS"),
                _i(row, "SURVEY_EROSION_SHEET"),
                _i(row, "SURVEY_EROSION_RILL"),
                _i(row, "SURVEY_EROSION_GULLY"),
                _i(row, "SURVEY_EROSION_MASS"),
                _i(row, "SURVEY_EROSION_DEP"),
                _i(row, "SURVEY_EROSION_WIND"),
            )
            if result.endswith(" 1"):
                inserted += 1
    return inserted


async def load_lucas_organic(csv_path: Path) -> int:
    df = pd.read_csv(csv_path)
    pool = await get_pool()
    inserted = 0
    depth_cols = [
        "SURVEY_SOIL_ORG_DEPTH_P_CM",
        "SURVEY_SOIL_ORG_DEPTH_N_CM",
        "SURVEY_SOIL_ORG_DEPTH_E_CM",
        "SURVEY_SOIL_ORG_DEPTH_S_CM",
        "SURVEY_SOIL_ORG_DEPTH_W_CM",
    ]
    reach40_cols = [
        "SURVEY_SOIL_ORG_DEPTH_P_40_CM",
        "SURVEY_SOIL_ORG_DEPTH_N_40_CM",
        "SURVEY_SOIL_ORG_DEPTH_E_40_CM",
        "SURVEY_SOIL_ORG_DEPTH_S_40_CM",
        "SURVEY_SOIL_ORG_DEPTH_W_40_CM",
    ]
    async with pool.acquire() as conn, conn.transaction():
        for _, row in df.iterrows():
            depths = [_f(row, c) for c in depth_cols]
            depths = [d for d in depths if d is not None]
            depth_mean = sum(depths) / len(depths) if depths else None
            reaches_40 = any(_i(row, c) == 1 for c in reach40_cols) or None
            result = await conn.execute(
                _ORGANIC_UPSERT,
                int(row["POINT_ID"]),
                _i(row, "SURVEY_SOIL_ORG_CULTIVATED"),
                depth_mean,
                1 if reaches_40 else (0 if reaches_40 is False else None),
                _i(row, "SURVEY_SOIL_ORG_TAKEN"),
            )
            if result.endswith(" 1"):
                inserted += 1
    return inserted


def _f(row, col):
    v = row.get(col)
    try:
        return float(v) if pd.notna(v) else None
    except (TypeError, ValueError):
        return None


def _i(row, col):
    v = row.get(col)
    try:
        return int(v) if pd.notna(v) else None
    except (TypeError, ValueError):
        return None
