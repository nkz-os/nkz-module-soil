import pytest
from nkz_soil.providers.igme import IgmeProvider


@pytest.fixture
def provider():
    return IgmeProvider()


def test_provider_metadata(provider):
    assert provider.name == "igme"
    assert provider.priority == 30
