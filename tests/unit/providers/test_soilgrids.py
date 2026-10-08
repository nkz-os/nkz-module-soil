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


_CRS = "EPSG:3035"  # any projected CRS: the point must be reprojected


def _mosaic(tmp_path, lon, lat, value):
    """Two 5x5 tiles side by side plus a VRT that stitches them, all local.

    The pixel under (lon, lat) is pixel (2, 2) of the SECOND tile.
    """
    import numpy as np
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import from_origin
    from rasterio.warp import transform as warp_transform

    xs, ys = warp_transform("EPSG:4326", _CRS, [lon], [lat])
    x0, y0 = xs[0] - 750, ys[0] + 250  # mosaic origin: 7.5 px left, 2.5 px up
    (tmp_path / "t").mkdir()
    for i, name in enumerate(("a", "b")):
        data = np.full((5, 5), -32768, dtype="int16")
        if name == "b":
            data[2, 2] = value
        with rasterio.open(
            tmp_path / "t" / f"{name}.tif", "w", driver="GTiff", height=5, width=5, count=1,
            dtype="int16", crs=_CRS, nodata=-32768,
            transform=from_origin(x0 + i * 500, y0, 100, 100),
        ) as dst:
            dst.write(data, 1)
    wkt = CRS.from_string(_CRS).to_wkt()
    src = '<SrcRect xOff="0" yOff="0" xSize="5" ySize="5" />'
    vrt = (
        f'<VRTDataset rasterXSize="10" rasterYSize="5"><SRS>{wkt}</SRS>'
        f"<GeoTransform>{x0}, 100, 0, {y0}, 0, -100</GeoTransform>"
        '<VRTRasterBand dataType="Int16" band="1">'
        '<ComplexSource><SourceFilename relativeToVRT="1">./t/a.tif</SourceFilename>'
        f'{src}<DstRect xOff="0" yOff="0" xSize="5" ySize="5" /></ComplexSource>'
        '<ComplexSource><SourceFilename relativeToVRT="1">./t/b.tif</SourceFilename>'
        f'{src}<DstRect xOff="5" yOff="0" xSize="5" ySize="5" /></ComplexSource>'
        "</VRTRasterBand></VRTDataset>"
    )
    return f"file://{tmp_path}/m.vrt", vrt


class _LocalRasterio:
    """rasterio, but /vsicurl/file://... opens the local file."""

    @staticmethod
    def open(p):
        import rasterio

        return rasterio.open(p.replace("/vsicurl/", "").replace("file://", ""))

    @staticmethod
    def Env(**kw):
        import rasterio

        return rasterio.Env(**kw)


@pytest.fixture
def mosaic(tmp_path, monkeypatch):
    from nkz_soil.providers import soilgrids_vrt

    lon, lat = -2.0788, 42.6400
    url, vrt = _mosaic(tmp_path, lon, lat, 271)
    fetched = []
    monkeypatch.setattr(soilgrids_vrt, "_cache", {})
    monkeypatch.setattr(soilgrids_vrt, "_fetch_text", lambda u: fetched.append(u) or vrt)
    return url, lon, lat, fetched


def test_cog_pixel_reads_only_the_tile_under_the_point(provider, mosaic):
    """lon/lat is reprojected to the mosaic CRS, its tile resolved, and read."""
    url, lon, lat, _ = mosaic
    assert provider._read_cog_pixel(_LocalRasterio, url, lon, lat) == 271.0


def test_cog_pixel_outside_every_tile_is_none(provider, mosaic):
    url, *_ = mosaic
    assert provider._read_cog_pixel(_LocalRasterio, url, 10.0, 50.0) is None


def test_vrt_is_downloaded_once_per_process(provider, mosaic):
    url, lon, lat, fetched = mosaic
    for _ in range(3):
        provider._read_cog_pixel(_LocalRasterio, url, lon, lat)
    assert fetched == [url]


def test_locate_maps_dst_to_src_rect():
    """Edge tiles can have a SrcRect that differs from their DstRect."""
    from nkz_soil.providers.soilgrids_vrt import TileIndex, TileSource

    idx = TileIndex(crs_wkt="", geotransform=(0, 1, 0, 0, 0, -1), sources=(
        TileSource(url="u", src=(10, 20, 100, 100), dst=(50, 60, 100, 100)),
    ))
    assert idx.locate(55, 61) == ("u", 15, 21)
    assert idx.locate(49, 61) is None


@respx.mock
@pytest.mark.asyncio
async def test_rest_divides_by_d_factor_and_reports_carbon_in_percent(provider):
    """d_factor converts mapped units to conventional ones (divide), and soil
    organic carbon (g/kg conventional) is canonical in %."""
    layer = lambda name, mean, f: {
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
