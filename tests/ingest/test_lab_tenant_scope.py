from unittest.mock import patch, AsyncMock, MagicMock

from nkz_soil.providers.lab_analysis import LabAnalysisProvider
from nkz_soil.storage import orion as O
from nkz_soil.models.domain import SoilProperty, DepthInterval

from .conftest import _run


def test_lab_provider_scopes_orion_to_current_tenant():
    captured = {}

    def fake_orion(tenant_id=None):
        captured["tenant"] = tenant_id
        m = MagicMock()
        m.__aenter__ = AsyncMock(return_value=m)
        m.__aexit__ = AsyncMock(return_value=None)
        m.query_entities = AsyncMock(return_value=[])
        return m

    token = O.set_current_tenant("tenant-xyz")
    try:
        with patch("nkz_soil.providers.lab_analysis.OrionClient", side_effect=fake_orion):
            _run(LabAnalysisProvider().fetch(
                {"type": "Point", "coordinates": [0, 0]},
                [SoilProperty.CLAY], [DepthInterval(0, 5)]))
    finally:
        O._TENANT.reset(token)

    assert captured["tenant"] == "tenant-xyz"
