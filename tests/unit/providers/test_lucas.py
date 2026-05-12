import pytest
from nkz_soil.providers.lucas import LucasPointsProvider


@pytest.fixture
def provider():
    return LucasPointsProvider()


def test_provider_metadata(provider):
    assert provider.name == "lucas"
    assert provider.priority == 25
