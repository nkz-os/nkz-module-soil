import pytest
from datetime import timedelta
from nkz_soil.providers.base import CircuitBreaker, ProviderRegistry


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
    cb = CircuitBreaker(max_failures=1, isolate_seconds=-1)  # negative = already expired
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
