import pytest
from nkz_soil.providers.lucas import LucasProvider


@pytest.fixture
def provider():
    return LucasProvider()


def test_provider_metadata(provider):
    assert provider.name == "lucas"
    assert provider.priority == 25
