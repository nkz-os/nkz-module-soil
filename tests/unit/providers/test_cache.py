import pytest
from nkz_soil.providers.cache import (
    _compute_cache_key,
    _get_ttl,
    _serialize_result,
    _deserialize_result,
    ProviderCache,
)
from nkz_soil.models.domain import SoilProperty, DepthInterval, SoilDataResult, Horizon


def test_cache_key_deterministic():
    geometry = {"type": "Point", "coordinates": [-2.0, 42.0]}
    props = [SoilProperty.SAND, SoilProperty.CLAY]
    depths = [DepthInterval(0, 5)]
    k1 = _compute_cache_key("soilgrids", geometry, props, depths)
    k2 = _compute_cache_key("soilgrids", geometry, props, depths)
    assert k1 == k2


def test_cache_key_different_providers():
    geometry = {"type": "Point", "coordinates": [-2.0, 42.0]}
    props = [SoilProperty.SAND]
    depths = [DepthInterval(0, 5)]
    k1 = _compute_cache_key("soilgrids", geometry, props, depths)
    k2 = _compute_cache_key("idena", geometry, props, depths)
    assert k1 != k2


def test_cache_key_different_geometry():
    props = [SoilProperty.SAND]
    depths = [DepthInterval(0, 5)]
    g1 = {"type": "Point", "coordinates": [-2.0, 42.0]}
    g2 = {"type": "Point", "coordinates": [-1.0, 43.0]}
    k1 = _compute_cache_key("soilgrids", g1, props, depths)
    k2 = _compute_cache_key("soilgrids", g2, props, depths)
    assert k1 != k2


def test_get_ttl_revisable():
    assert _get_ttl("idena") == 2592000
    assert _get_ttl("igme") == 2592000
    assert _get_ttl("bgs") == 2592000


def test_get_ttl_baseline():
    assert _get_ttl("soilgrids") == 31536000
    assert _get_ttl("lucas") == 31536000


def test_serialize_deserialize_roundtrip():
    result = SoilDataResult(
        provider="soilgrids",
        horizons=[
            Horizon(depth_from=0, depth_to=5, sand=45.0, clay=20.0, ph=6.5),
            Horizon(depth_from=5, depth_to=15, sand=40.0, clay=25.0, ph=6.8),
        ],
        uncertainty=0.25,
        geometry={"type": "Point", "coordinates": [-2.0, 42.0]},
        attribution="ISRIC SoilGrids",
    )
    serialized = _serialize_result(result)
    deserialized = _deserialize_result(serialized)
    assert deserialized.provider == result.provider
    assert len(deserialized.horizons) == 2
    assert deserialized.horizons[0].sand == 45.0
    assert deserialized.horizons[1].ph == 6.8
    assert deserialized.uncertainty == 0.25
    assert deserialized.attribution == "ISRIC SoilGrids"
