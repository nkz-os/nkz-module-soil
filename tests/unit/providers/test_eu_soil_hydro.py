import pytest
from nkz_soil.providers.eu_soil_hydro import EuSoilHydroGridsProvider


@pytest.fixture
def provider():
    return EuSoilHydroGridsProvider()


def test_provider_metadata(provider):
    assert provider.name == "eu_soil_hydro"
    assert provider.priority == 20
