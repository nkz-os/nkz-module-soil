"""Loader: idempotent bulk import of LUCAS topsoil CSV into PostGIS."""
from __future__ import annotations
from pathlib import Path
import asyncpg

from nkz_soil.ingest.lucas_loader import load_lucas_topsoil
from nkz_soil.storage import pg as pg_module

from .conftest import _run

FIXTURE = Path(__file__).parent / "fixtures" / "lucas_topsoil_sample.csv"


def test_loader_inserts_expected_rows(pg_dsn):
    pg_module._POOL = None  # rebind in this loop
    n = _run(load_lucas_topsoil(FIXTURE))
    assert n == 3


def test_loader_is_idempotent(pg_dsn):
    pg_module._POOL = None
    _run(load_lucas_topsoil(FIXTURE))
    pg_module._POOL = None  # close old pool before creating a new loop
    _run(load_lucas_topsoil(FIXTURE))

    async def _count():
        conn = await asyncpg.connect(pg_dsn)
        try:
            return await conn.fetchval("SELECT COUNT(*) FROM soil_module.lucas_topsoil_2018")
        finally:
            await conn.close()

    assert _run(_count()) == 3
