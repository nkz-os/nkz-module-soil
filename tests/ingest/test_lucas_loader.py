"""Loader: idempotent bulk import of LUCAS topsoil CSV into PostGIS."""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from nkz_soil.ingest.lucas_loader import load_lucas_topsoil
from nkz_soil.storage import pg as pg_module

FIXTURE = Path(__file__).parent / "fixtures" / "lucas_topsoil_sample.csv"


@pytest.fixture(scope="module")
def pg_dsn():
    with PostgresContainer("postgis/postgis:16-3.4") as pg:
        dsn = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        os.environ["SOIL_PG_DSN"] = dsn
        pg_module._POOL = None  # ensure fresh pool per test module

        async def _migrate():
            conn = await asyncpg.connect(dsn)
            try:
                # postgis/postgis image ships the extension but it must be created
                await conn.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
                root = Path(__file__).resolve().parents[2] / "backend" / "migrations"
                for m in sorted(root.glob("00[12]_*.sql")):
                    await conn.execute(m.read_text())
            finally:
                await conn.close()

        asyncio.new_event_loop().run_until_complete(_migrate())
        yield dsn
        # Discard the cached pool reference — the pool is bound to a closed
        # event loop (each _run() creates and closes its own loop), so calling
        # close() on it raises RuntimeError. The container is being torn down
        # anyway, so simply nulling out the reference is sufficient.
        pg_module._POOL = None


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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
