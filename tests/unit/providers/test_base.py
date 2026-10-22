from datetime import timedelta

from nkz_soil.providers.base import (
    CircuitBreaker,
    ProviderRegistry,
    geometry_intersects_bbox,
)


class FakeProvider:
    name = "test"
    priority = 10
    geographic_scope = None
    update_cadence = timedelta(days=1)


def test_circuit_breaker_opens_after_max_failures():
    cb = CircuitBreaker(max_failures=3, isolate_seconds=10)
    cb.record_failure("test-provider")
    cb.record_failure("test-provider")
    assert not cb.is_open("test-provider")
    cb.record_failure("test-provider")
    assert cb.is_open("test-provider")


def test_circuit_breaker_resets_on_success():
    cb = CircuitBreaker(max_failures=3, isolate_seconds=10)
    cb.record_failure("test-provider")
    cb.record_failure("test-provider")
    cb.record_success("test-provider")
    assert not cb.is_open("test-provider")


def test_circuit_breaker_auto_resets_after_timeout():
    cb = CircuitBreaker(max_failures=1, isolate_seconds=-1)
    cb.record_failure("test-provider")
    assert not cb.is_open("test-provider")


def test_registry_sorts_by_priority():
    registry = ProviderRegistry()

    class LowPrio(FakeProvider):
        name = "low"
        priority = 10

    class HighPrio(FakeProvider):
        name = "high"
        priority = 100

    registry.register(LowPrio())
    registry.register(HighPrio())
    assert registry.get_all()[0].name == "high"
    assert registry.get_all()[1].name == "low"


def test_bbox_global_always_true():
    point = {"type": "Point", "coordinates": [-1.6, 42.8]}
    assert geometry_intersects_bbox(point, (-180, -90, 180, 90)) is True


def test_bbox_point_inside():
    point = {"type": "Point", "coordinates": [-1.6, 42.8]}
    assert geometry_intersects_bbox(point, (-2.5, 41.5, -0.5, 43.5)) is True


def test_bbox_point_outside():
    point = {"type": "Point", "coordinates": [0.0, 51.5]}
    assert geometry_intersects_bbox(point, (-2.5, 41.5, -0.5, 43.5)) is False


def test_bbox_polygon_intersects():
    polygon = {
        "type": "Polygon",
        "coordinates": [[[-2.0, 42.0], [-1.0, 42.0], [-1.0, 43.0], [-2.0, 43.0], [-2.0, 42.0]]],
    }
    assert geometry_intersects_bbox(polygon, (-2.5, 41.5, -0.5, 43.5)) is True


def test_bbox_polygon_outside():
    polygon = {
        "type": "Polygon",
        "coordinates": [[[0.0, 51.0], [1.0, 51.0], [1.0, 52.0], [0.0, 52.0], [0.0, 51.0]]],
    }
    assert geometry_intersects_bbox(polygon, (-2.5, 41.5, -0.5, 43.5)) is False


def test_bbox_invalid_geometry_returns_true():
    assert geometry_intersects_bbox({"type": "Invalid"}, (-10, 35, 5, 44)) is True
