import pytest
from nkz_soil.providers.idena import IdenaProvider


@pytest.fixture
def provider():
    return IdenaProvider()


def test_provider_metadata(provider):
    assert provider.name == "idena"
    assert provider.priority == 40


def test_covers_geometry(provider):
    geometry = {"type": "Polygon", "coordinates": [[[-1.6, 42.8], [-1.5, 42.8], [-1.5, 42.9], [-1.6, 42.8]]]}
    assert provider.covers(geometry) is True
