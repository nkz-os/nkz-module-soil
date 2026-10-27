import pytest
from nkz_soil.providers.lucas import LucasProvider


@pytest.fixture
def provider():
    return LucasProvider()


@pytest.mark.skip(reason="LUCAS rewritten as PostGIS KNN in T17; name is now 'LUCAS'. Covered by tests/ingest/test_lucas_postgis_provider.py")
def test_provider_metadata(provider):
    assert provider.name == "lucas"
    assert provider.priority == 25


@pytest.mark.asyncio
async def test_values_in_polygon_means_and_converts_oc_to_percent():
    from unittest.mock import AsyncMock, MagicMock, patch

    rows = [
        {"clay_pct": 20, "sand_pct": 40, "silt_pct": 40, "oc_g_kg": 10, "ph_h2o": 7.0},
        {"clay_pct": 30, "sand_pct": 30, "silt_pct": 40, "oc_g_kg": 20, "ph_h2o": None},
    ]
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    with patch("nkz_soil.providers.lucas.get_pool", AsyncMock(return_value=pool)):
        vals = await LucasProvider().values_in_polygon({"type": "Polygon", "coordinates": []})
        conn.fetch.return_value = []
        none = await LucasProvider().values_in_polygon({"type": "Polygon", "coordinates": []})
    assert vals == {"sand": 35.0, "silt": 40.0, "clay": 25.0, "organic_carbon": 1.5, "ph": 7.0}
    assert none is None
