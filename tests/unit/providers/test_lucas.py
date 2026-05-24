import pytest
from nkz_soil.providers.lucas import LucasProvider


@pytest.fixture
def provider():
    return LucasProvider()


@pytest.mark.skip(reason="LUCAS rewritten as PostGIS KNN in T17; name is now 'LUCAS'. Covered by tests/ingest/test_lucas_postgis_provider.py")
def test_provider_metadata(provider):
    assert provider.name == "lucas"
    assert provider.priority == 25
