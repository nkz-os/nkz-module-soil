"""Tests for the defensive geometry simplification in the ingest worker.

Raw cadastral polygons can carry hundreds of vertices (e.g. 486 for a
217 ha parcel), which makes Orion-LD geo-queries and entity payloads
extremely slow. `_simplify_geometry` must collapse those to a manageable
vertex count without raising.
"""

import math

from nkz_soil.workers.ingest import (
    _GEOMETRY_SIMPLIFY_TOLERANCE_M,
    _simplify_geometry,
)


def _dense_polygon(n_points: int = 486, radius_deg: float = 0.001) -> dict:
    cx, cy = -1.6, 42.6
    coords = [
        [cx + radius_deg * math.cos(2 * math.pi * i / n_points),
         cy + radius_deg * math.sin(2 * math.pi * i / n_points)]
        for i in range(n_points)
    ]
    coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


def test_dense_polygon_is_simplified():
    geom = _dense_polygon()
    out = _simplify_geometry(geom)
    assert out["type"] == "Polygon"
    n_in = len(geom["coordinates"][0])
    n_out = len(out["coordinates"][0])
    assert n_out < n_in // 4


def test_simple_polygon_stays_a_polygon():
    geom = {"type": "Polygon", "coordinates": [[[0, 0], [0.0001, 0], [0.0001, 0.0001], [0, 0]]]}
    assert _simplify_geometry(geom)["type"] == "Polygon"


def test_non_polygon_returned_unchanged():
    geom = {"type": "Point", "coordinates": [-1.6, 42.6]}
    assert _simplify_geometry(geom) is geom


def test_none_returned_unchanged():
    assert _simplify_geometry(None) is None


def test_tolerance_is_one_meter():
    assert _GEOMETRY_SIMPLIFY_TOLERANCE_M == 1.0
