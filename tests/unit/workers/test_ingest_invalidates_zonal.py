from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_ingest_invalidates_zonal_cache_of_that_parcel():
    from nkz_soil.workers.ingest import ingest_parcel

    orion = AsyncMock()
    orion.__aenter__ = AsyncMock(return_value=orion)
    orion.__aexit__ = AsyncMock(return_value=None)
    orion.get_entity = AsyncMock(return_value=None)
    cb = AsyncMock()
    cb.is_open = AsyncMock(return_value=False)
    ctx = {"registry": MagicMock(), "circuit_breaker": cb, "cache": AsyncMock()}
    ctx["registry"].get_all.return_value = []
    with (
        patch("nkz_soil.workers.ingest.OrionClient", return_value=orion),
        patch("nkz_soil.workers.ingest.invalidate_parcel", AsyncMock()) as inv,
    ):
        await ingest_parcel(ctx, "p1", "acme", {"type": "Point", "coordinates": [-1.6, 42.8]}, "v1")
    inv.assert_awaited_once_with("acme", "p1")
