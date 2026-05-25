"""LUCAS PostGIS KNN provider returns weighted average of nearest N points."""
from __future__ import annotations
from pathlib import Path
import pytest

from nkz_soil.ingest.lucas_loader import load_lucas_topsoil
from nkz_soil.providers.lucas import LucasProvider
from nkz_soil.models.domain import SoilProperty, DepthInterval
from nkz_soil.storage import pg as pg_module

from .conftest import _run

FIXTURE = Path(__file__).parent / "fixtures" / "lucas_topsoil_sample.csv"
_DEPTHS = [DepthInterval(0, 5), DepthInterval(5, 15), DepthInterval(15, 30)]
_PROPS = [SoilProperty.CLAY, SoilProperty.SAND, SoilProperty.ORGANIC_CARBON]


@pytest.fixture(scope="module")
def loaded(pg_dsn):
    pg_module._POOL = None
    _run(load_lucas_topsoil(FIXTURE))
    return pg_dsn


def test_knn_returns_attributes_from_nearest_point(loaded):
    pg_module._POOL = None
    provider = LucasProvider(buffer_km=5, k=1)
    geom = {"type": "Point", "coordinates": [-1.645, 42.815]}
    res = _run(provider.fetch(geom, _PROPS, _DEPTHS))
    assert res is not None
    assert res.provider == "LUCAS"
    assert res.license == "JRC-LUCAS-2018"
    assert res.redistributable is True
    assert res.priority == 25
    top = res.horizons[0]
    assert abs(top.clay - 25.0) < 0.01
    assert abs(top.sand - 42.0) < 0.01
    # OC stored as 18.5 g/kg in the fixture; provider emits percent (÷10).
    assert abs(top.organic_carbon - 1.85) < 0.01


def test_knn_returns_none_outside_buffer(loaded):
    pg_module._POOL = None
    provider = LucasProvider(buffer_km=5, k=3)
    geom = {"type": "Point", "coordinates": [-30.0, 40.0]}
    res = _run(provider.fetch(geom, _PROPS, _DEPTHS))
    assert res is None


def test_knn_returns_inverse_distance_weighted_for_k_gt_1(loaded):
    pg_module._POOL = None
    provider = LucasProvider(buffer_km=2000, k=3)
    geom = {"type": "Point", "coordinates": [-1.645, 42.815]}
    res = _run(provider.fetch(geom, _PROPS, _DEPTHS))
    assert res is not None
    assert 15.0 < res.horizons[0].clay < 30.0
