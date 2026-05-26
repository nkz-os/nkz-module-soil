from pathlib import Path

from nkz_soil.storage import pg as pg_module

from .conftest import _run

MIG = Path(__file__).resolve().parents[2] / "backend" / "migrations" / "008_lucas_texture_raster_index.sql"


def test_creates_restricted_texture_table(pg_dsn):
    pg_module._POOL = None

    async def go():
        pool = await pg_module.get_pool()
        async with pool.acquire() as c:
            await c.execute(MIG.read_text())
            cols = await c.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='soil_module' AND table_name='lucas_texture_raster_index'")
            names = {r["column_name"] for r in cols}
            assert {"variable", "storage_uri", "bbox", "crs", "redistributable", "license"} <= names
            default = await c.fetchval(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_schema='soil_module' AND table_name='lucas_texture_raster_index' "
                "AND column_name='redistributable'")
            assert "false" in (default or "").lower()

    _run(go())
