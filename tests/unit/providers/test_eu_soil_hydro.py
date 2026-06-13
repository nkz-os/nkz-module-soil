import pytest
from nkz_soil.providers.eu_soil_hydro import EuSoilHydroGridsProvider


@pytest.fixture
def provider():
    return EuSoilHydroGridsProvider()


def test_provider_metadata(provider):
    assert provider.name == "eu_soil_hydro"
    assert provider.priority == 20


@pytest.mark.asyncio
async def test_fetch_is_marked_non_redistributable(provider):
    """EU-SoilHydroGrids is 'non-commercial use only' → results must carry
    redistributable=False so the suppression boundary withholds raw values."""
    result = await provider.fetch(
        {"type": "Point", "coordinates": [-1.5, 42.0]}, [], []
    )
    assert result.redistributable is False
    assert result.license is not None
