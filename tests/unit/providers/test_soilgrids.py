from datetime import timedelta
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from nkz_soil.models.domain import DepthInterval, SoilProperty
from nkz_soil.providers.soilgrids import SoilGridsProvider


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


def _projected_raster(tmp_path, lon, lat, value):
    """A small GeoTIFF in a projected CRS (metres) with `value` under (lon, lat)."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import transform as warp_transform

    xs, ys = warp_transform("EPSG:4326", "EPSG:3035", [lon], [lat])
    data = np.full((5, 5), -32768, dtype="int16")
    data[2, 2] = value
    path = tmp_path / "clay.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=5, width=5, count=1, dtype="int16",
        crs="EPSG:3035", nodata=-32768,
        transform=from_origin(xs[0] - 250, ys[0] + 250, 100, 100),
    ) as dst:
        dst.write(data, 1)
    return path


def test_cog_pixel_is_read_in_the_raster_crs(provider, tmp_path):
    """lon/lat must be reprojected to the COG's CRS before indexing."""
    import rasterio

    lon, lat = -2.0788, 42.6400
    path = _projected_raster(tmp_path, lon, lat, 271)

    class _Shim:
        @staticmethod
        def open(p):
            return rasterio.open(p.replace("/vsicurl/", ""))

    assert provider._read_cog_pixel(_Shim, str(path), lon, lat) == 271.0


def test_cog_pixel_outside_raster_is_none(provider, tmp_path):
    import rasterio

    path = _projected_raster(tmp_path, -2.0788, 42.6400, 271)

    class _Shim:
        @staticmethod
        def open(p):
            return rasterio.open(p.replace("/vsicurl/", ""))

    assert provider._read_cog_pixel(_Shim, str(path), 10.0, 50.0) is None


@respx.mock
@pytest.mark.asyncio
async def test_rest_divides_by_d_factor_and_reports_carbon_in_percent(provider):
    """d_factor converts mapped units to conventional ones (divide), and soil
    organic carbon (g/kg conventional) is canonical in %."""
    layer = lambda name, mean, f: {  # noqa: E731
        "name": name, "unit_measure": {"d_factor": f},
        "depths": [{"range": {"top_depth": 0, "bottom_depth": 5}, "values": {"mean": mean}}],
    }
    respx.get("https://rest.isric.org/soilgrids/v2.0/properties/query").mock(
        return_value=Response(200, json={"properties": {"layers": [
            layer("sand", 250, 10), layer("soc", 150, 10), layer("clay", None, 10),
        ]}})
    )
    with patch("nkz_soil.providers.soilgrids._HAS_RASTERIO", False):
        result = await provider.fetch(
            geometry={"type": "Point", "coordinates": [-2.07, 42.64]},
            properties=[SoilProperty.SAND, SoilProperty.ORGANIC_CARBON, SoilProperty.CLAY],
            depths=[DepthInterval(depth_from=0, depth_to=5)],
        )
    h = result.horizons[0]
    assert h.sand == 25.0
    assert h.organic_carbon == 1.5
    assert h.clay is None  # masked pixel: no value, not 0
