import asyncio

import nkz_soil.workers.ingest as W


def test_texture_provider_registered_in_worker():
    ctx = {}
    asyncio.new_event_loop().run_until_complete(W.startup(ctx))
    assert "LUCAS-Texture" in {p.name for p in ctx["registry"].get_all()}
