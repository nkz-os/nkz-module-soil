"""LUCAS PostGIS KNN provider returns weighted average of nearest N points."""
from __future__ import annotations
from pathlib import Path
import pytest

from nkz_soil.ingest.lucas_loader import load_lucas_topsoil
from nkz_soil.providers.lucas import LucasProvider
from nkz_soil.storage import pg as pg_module

from .conftest import _run

FIXTURE = Path(__file__).parent / "fixtures" / "lucas_topsoil_sample.csv"


@pytest.fixture(scope="module")
def loaded(pg_dsn):
    pg_module._POOL = None
    _run(load_lucas_topsoil(FIXTURE))
    return pg_dsn


def test_knn_returns_attributes_from_nearest_point(loaded):
    pg_module._POOL = None
    provider = LucasProvider(buffer_km=5, k=1)
    res = _run(provider.fetch(lat=42.815, lon=-1.645))
    assert res is not None
    assert res.source_tag == "LUCAS-2018"
    assert res.license == "JRC-LUCAS-2018"
    assert res.entitlement_required == "open"
    assert res.priority == 25
    assert abs(res.attributes["clayContent"] - 25.0) < 0.01
    assert abs(res.attributes["sandContent"] - 42.0) < 0.01
    assert abs(res.attributes["organicCarbon"] - 18.5) < 0.01


def test_knn_returns_none_outside_buffer(loaded):
    pg_module._POOL = None
    provider = LucasProvider(buffer_km=5, k=3)
    res = _run(provider.fetch(lat=40.0, lon=-30.0))
    assert res is None


def test_knn_returns_inverse_distance_weighted_for_k_gt_1(loaded):
    pg_module._POOL = None
    provider = LucasProvider(buffer_km=2000, k=3)
    res = _run(provider.fetch(lat=42.815, lon=-1.645))
    assert res is not None
    assert 15.0 < res.attributes["clayContent"] < 30.0
