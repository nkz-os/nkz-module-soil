import pytest
from unittest.mock import AsyncMock, patch
from nkz_soil.providers.lab_analysis import LabAnalysisProvider
from nkz_soil.models.domain import SoilProperty, DepthInterval


@pytest.fixture
def provider():
    return LabAnalysisProvider()


def test_highest_priority(provider):
    assert provider.priority == 100


@patch("nkz_soil.providers.lab_analysis.OrionClient")
@pytest.mark.asyncio
async def test_fetch_returns_lab_horizons(mock_orion, provider):
    mock_client = AsyncMock()
    mock_client.query_entities.return_value = [
        {
            "id": "urn:ngsi-ld:SoilSamplingPoint:sp-1",
            "location": {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [-1.6, 42.8]}},
            "horizons": {"type": "Property", "value": [
                {"depthFrom": 0, "depthTo": 30, "sand": 45, "silt": 35, "clay": 20, "ph": 6.8, "organicCarbon": 2.1, "bulkDensity": 1.32}
            ]},
        }
    ]
    mock_orion.return_value.__aenter__.return_value = mock_client

    result = await provider.fetch(
        geometry={"type": "Point", "coordinates": [-1.6, 42.8]},
        properties=[SoilProperty.SAND, SoilProperty.PH],
        depths=[DepthInterval(depth_from=0, depth_to=30)],
    )

    assert result.provider == "lab_analysis"
    assert result.horizons[0].sand == 45
    assert result.horizons[0].ph == 6.8
    assert result.uncertainty == 0.02


@patch("nkz_soil.providers.lab_analysis.OrionClient")
@pytest.mark.asyncio
async def test_no_points_returns_empty(mock_orion, provider):
    mock_client = AsyncMock()
    mock_client.query_entities.return_value = []
    mock_orion.return_value.__aenter__.return_value = mock_client

    result = await provider.fetch(
        geometry={"type": "Point", "coordinates": [0, 0]},
        properties=[SoilProperty.PH],
        depths=[DepthInterval(depth_from=0, depth_to=30)],
    )

    assert len(result.horizons) == 0
