import pytest
import respx
from httpx import Response
from datetime import timedelta
from unittest.mock import patch
from nkz_soil.providers.soilgrids import SoilGridsProvider
from nkz_soil.models.domain import SoilProperty, DepthInterval


@pytest.fixture
def provider():
    return SoilGridsProvider()


def test_provider_metadata(provider):
    assert provider.name == "soilgrids"
    assert provider.priority == 10
    assert isinstance(provider.update_cadence, timedelta)
    assert provider.geographic_scope is not None


def test_covers_anywhere(provider):
    geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    assert provider.covers(geometry) is True


@respx.mock
@pytest.mark.asyncio
async def test_fetch_returns_horizons(provider):
    """Test REST API fetch path (COG disabled via mock)."""
    mock_response = {
        "properties": {
            "layers": [
                {
                    "name": "sand",
                    "unit_measure": {"d_factor": 1},
                    "depths": [
                        {
                            "range": {"top_depth": 0, "bottom_depth": 5},
                            "values": {"mean": 45},
                        }
                    ],
                },
                {
                    "name": "clay",
                    "unit_measure": {"d_factor": 1},
                    "depths": [
                        {
                            "range": {"top_depth": 0, "bottom_depth": 5},
                            "values": {"mean": 20},
                        }
                    ],
                },
                {
                    "name": "silt",
                    "unit_measure": {"d_factor": 1},
                    "depths": [
                        {
                            "range": {"top_depth": 0, "bottom_depth": 5},
                            "values": {"mean": 35},
                        }
                    ],
                },
            ]
        }
    }

    respx.get("https://rest.isric.org/soilgrids/v2.0/properties/query").mock(
        return_value=Response(200, json=mock_response)
    )

    # Force REST path by disabling rasterio
    with patch("nkz_soil.providers.soilgrids._HAS_RASTERIO", False):
        result = await provider.fetch(
            geometry={
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
            },
            properties=[SoilProperty.SAND, SoilProperty.CLAY, SoilProperty.SILT],
            depths=[DepthInterval(depth_from=0, depth_to=5)],
        )

    assert result.provider == "soilgrids"
    assert len(result.horizons) > 0
    assert result.horizons[0].sand == 45
    assert result.horizons[0].clay == 20
    assert result.horizons[0].silt == 35


@respx.mock
@pytest.mark.asyncio
async def test_fetch_rest_skips_nodata_ph(provider):
    mock_response = {
        "properties": {
            "layers": [
                {
                    "name": "phh2o",
                    "unit_measure": {"d_factor": 1},
                    "depths": [
                        {
                            "range": {"top_depth": 0, "bottom_depth": 5},
                            "values": {"mean": -3276.8},
                        }
                    ],
                },
            ]
        }
    }
    respx.get("https://rest.isric.org/soilgrids/v2.0/properties/query").mock(
        return_value=Response(200, json=mock_response)
    )
    with patch("nkz_soil.providers.soilgrids._HAS_RASTERIO", False):
        result = await provider.fetch(
            geometry={
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
            },
            properties=[SoilProperty.PH],
            depths=[DepthInterval(depth_from=0, depth_to=5)],
        )
    assert result.horizons[0].ph is None


@respx.mock
@pytest.mark.asyncio
async def test_health_ok(provider):
    respx.get("https://files.isric.org/soilgrids/latest/data/").mock(
        return_value=Response(200)
    )
    health = await provider.health()
    assert health.status == "ok"
    assert health.name == "soilgrids"
