from nkz_soil.api.routes.subscriptions import (
    _compute_parcel_hash,
    _expand_geometry,
    SUBSCRIPTION_ID,
)


def test_parcel_hash_deterministic():
    h1 = _compute_parcel_hash("p1", "tenant1", "v1")
    h2 = _compute_parcel_hash("p1", "tenant1", "v1")
    assert h1 == h2


def test_parcel_hash_different_versions():
    h1 = _compute_parcel_hash("p1", "tenant1", "v1")
    h2 = _compute_parcel_hash("p1", "tenant1", "v2")
    assert h1 != h2


def test_parcel_hash_different_tenants():
    h1 = _compute_parcel_hash("p1", "tenant1", "v1")
    h2 = _compute_parcel_hash("p1", "tenant2", "v1")
    assert h1 != h2


def test_expand_geometry_point():
    geometry = {"type": "Point", "coordinates": [-2.0, 42.0]}
    expanded = _expand_geometry(geometry, 50.0)
    assert expanded["type"] == "Polygon"
    coords = expanded["coordinates"][0]
    assert len(coords) == 5
    assert coords[0] == coords[-1]


def test_expand_geometry_polygon():
    geometry = {
        "type": "Polygon",
        "coordinates": [[[-2.0, 42.0], [-1.9, 42.0], [-1.9, 42.1], [-2.0, 42.1], [-2.0, 42.0]]],
    }
    expanded = _expand_geometry(geometry, 50.0)
    assert expanded["type"] == "Polygon"
    coords = expanded["coordinates"][0]
    min_lon = min(c[0] for c in coords)
    max_lon = max(c[0] for c in coords)
    min_lat = min(c[1] for c in coords)
    max_lat = max(c[1] for c in coords)
    assert min_lon < -2.0
    assert max_lon > -1.9
    assert min_lat < 42.0
    assert max_lat > 42.1


def test_expand_geometry_unknown_returns_original():
    geometry = {"type": "LineString", "coordinates": [[-2.0, 42.0], [-1.9, 42.1]]}
    expanded = _expand_geometry(geometry, 50.0)
    assert expanded == geometry


def test_subscription_id_constant():
    assert SUBSCRIPTION_ID == "urn:ngsi-ld:Subscription:soil-parcel-ingest"
