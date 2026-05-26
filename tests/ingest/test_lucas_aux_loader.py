"""Aux loaders insert expected rows + are idempotent."""
from __future__ import annotations
from pathlib import Path
import asyncpg
import os

from nkz_soil.ingest.lucas_loader import load_lucas_topsoil
from nkz_soil.ingest.lucas_aux_loader import (
    load_lucas_bulk_density, load_lucas_erosion,
    load_lucas_organic,
)
from nkz_soil.storage import pg as pg_module

from .conftest import _run

FIX = Path(__file__).parent / "fixtures"


def test_aux_loaders_insert_three_rows_each(pg_dsn):
    pg_module._POOL = None
    _run(load_lucas_topsoil(FIX / "lucas_topsoil_sample.csv"))
    pg_module._POOL = None
    assert _run(load_lucas_bulk_density(FIX / "lucas_bd_sample.csv")) == 3
    pg_module._POOL = None
    assert _run(load_lucas_erosion(FIX / "lucas_erosion_sample.csv")) == 3
    pg_module._POOL = None
    assert _run(load_lucas_organic(FIX / "lucas_organic_sample.csv")) == 3


def test_aux_loaders_idempotent(pg_dsn):
    pg_module._POOL = None
    _run(load_lucas_topsoil(FIX / "lucas_topsoil_sample.csv"))
    for _ in range(2):
        for fn, fname in [
            (load_lucas_bulk_density, "lucas_bd_sample.csv"),
            (load_lucas_erosion, "lucas_erosion_sample.csv"),
            (load_lucas_organic, "lucas_organic_sample.csv"),
        ]:
            pg_module._POOL = None
            _run(fn(FIX / fname))

    async def _counts():
        conn = await asyncpg.connect(os.environ["SOIL_PG_DSN"])
        try:
            return {
                "bd": await conn.fetchval("SELECT COUNT(*) FROM soil_module.lucas_bulk_density_2018"),
                "ero": await conn.fetchval("SELECT COUNT(*) FROM soil_module.lucas_erosion_2018"),
                "org": await conn.fetchval("SELECT COUNT(*) FROM soil_module.lucas_organic_2018"),
            }
        finally:
            await conn.close()
    counts = _run(_counts())
    assert counts == {"bd": 3, "ero": 3, "org": 3}
