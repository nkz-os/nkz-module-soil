import asyncio

import nkz_soil.workers.ingest as W


def test_startup_registers_all_providers():
    ctx = {}
    asyncio.new_event_loop().run_until_complete(W.startup(ctx))
    names = {p.name for p in ctx["registry"].get_all()}
    assert {"LUCAS", "ESDB-Raster", "soilgrids"} <= names
    assert len(ctx["registry"].get_all()) >= 8
