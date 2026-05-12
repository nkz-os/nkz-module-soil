import pytest
from unittest.mock import AsyncMock, patch
from nkz_soil.providers.iot_sensor import IotSensorProvider
from nkz_soil.models.domain import SoilProperty, DepthInterval


@pytest.fixture
def provider():
    return IotSensorProvider()


def test_priority_below_lab_above_public(provider):
    assert provider.priority == 90


@patch("nkz_soil.providers.iot_sensor.OrionClient")
@pytest.mark.asyncio
async def test_fetch_returns_ph_from_sensor(mock_orion, provider):
    mock_client = AsyncMock()
    mock_client.query_entities.return_value = [
        {
            "id": "urn:ngsi-ld:Device:sensor-ph-1",
            "category": {"type": "Property", "value": "soil_ph"},
            "value": {"type": "Property", "value": 6.5},
            "location": {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [-1.6, 42.8]}},
        }
    ]
    mock_orion.return_value.__aenter__.return_value = mock_client

    result = await provider.fetch(
        geometry={"type": "Polygon", "coordinates": [[[-1.61, 42.79], [-1.59, 42.79], [-1.59, 42.81], [-1.61, 42.79]]]},
        properties=[SoilProperty.PH],
        depths=[DepthInterval(depth_from=0, depth_to=30)],
    )

    assert result.provider == "iot_sensor"
    assert result.horizons[0].ph == 6.5
    assert result.uncertainty == 0.05


@patch("nkz_soil.providers.iot_sensor.OrionClient")
@pytest.mark.asyncio
async def test_no_sensors_returns_empty(mock_orion, provider):
    mock_client = AsyncMock()
    mock_client.query_entities.return_value = []
    mock_orion.return_value.__aenter__.return_value = mock_client

    result = await provider.fetch(
        geometry={"type": "Point", "coordinates": [0, 0]},
        properties=[SoilProperty.PH],
        depths=[DepthInterval(depth_from=0, depth_to=30)],
    )

    assert len(result.horizons) == 0
