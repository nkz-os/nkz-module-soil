import pytest
from nkz_soil.providers.bgs import BgsProvider


@pytest.fixture
def provider():
    return BgsProvider()


def test_provider_metadata(provider):
    assert provider.name == "bgs"
    assert provider.priority == 30
