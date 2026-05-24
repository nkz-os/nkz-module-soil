"""ESDB-raster provider samples a COG at given lat/lon and returns the value."""
from __future__ import annotations
import pytest

from nkz_soil.ingest.esdb_raster_loader import catalog_esdb_rasters
from nkz_soil.providers.esdb_raster import EsdbRasterProvider
from nkz_soil.storage import pg as pg_module

from .conftest import _run


@pytest.fixture(scope="module")
def cataloged(pg_dsn, minio_with_objects):
    """Apply migration 003 + populate esdb_raster_index from minio_with_objects fixture."""
    pg_module._POOL = None
    _run(catalog_esdb_rasters(bucket="nekazari-soil-raw", prefix="esdb/"))
    return pg_dsn


def test_sample_returns_band_value_within_bbox(cataloged):
    """The synthetic COG has values=42 across a 10x10 grid at EPSG:3035.

    bbox stored as raw EPSG:3035 coordinates in a 4326-typed column (test-only fixture).
    Pick a query point whose reprojected (3035) coords fall inside the raster.
    The raster's stored bbox WKT contains (west=2000000, east=2010000, south=2990000, north=3000000).
    Since the bbox is queried with ST_Contains using projected coords as lat/lon, we must
    use a query lat/lon that, when passed through ST_MakePoint(lon, lat), falls inside that polygon.
    """
    pg_module._POOL = None
    provider = EsdbRasterProvider(variables=["CLAY", "OC"])
    # Query point: lon=2005000 lat=2995000 — strictly inside the synthetic bbox polygon
    res = _run(provider.fetch(lat=2995000, lon=2005000))
    assert res is not None
    assert res.source_tag == "ESDB-Raster-v2"
    assert res.license == "JRC-ESDB-Raster-Attribution"
    assert res.entitlement_required == "open"
    assert res.priority == 18
    # The COG was filled with 42 everywhere
    assert res.attributes.get("clayContent") == 42.0
    assert res.attributes.get("organicCarbon") == 42.0


def test_sample_returns_none_outside_all_bboxes(cataloged):
    pg_module._POOL = None
    provider = EsdbRasterProvider(variables=["CLAY", "OC"])
    res = _run(provider.fetch(lat=0.0, lon=0.0))  # far outside synthetic bbox
    assert res is None
