import pytest
from nkz_soil.providers.metrics import ProviderMetrics


@pytest.fixture
def metrics():
    m = ProviderMetrics()
    yield m
    m.reset()


def test_record_fetch(metrics):
    metrics.record_fetch("soilgrids", 150.0)
    stats = metrics.get_latency_stats("soilgrids")
    assert stats["count"] == 1
    assert stats["avg"] == 150.0


def test_record_fetch_cache_hit(metrics):
    metrics.record_fetch("soilgrids", 0.0, from_cache=True)
    cache_stats = metrics.get_cache_stats("soilgrids")
    assert cache_stats["hits"] == 1
    assert cache_stats["misses"] == 0


def test_record_error(metrics):
    metrics.record_error("soilgrids")
    assert metrics.get_error_rate("soilgrids") > 0


def test_error_rate_zero_when_no_errors(metrics):
    metrics.record_fetch("soilgrids", 100.0)
    assert metrics.get_error_rate("soilgrids") == 0.0


def test_p95_calculation(metrics):
    for i in range(100):
        metrics.record_fetch("soilgrids", float(i))
    stats = metrics.get_latency_stats("soilgrids")
    assert stats["p95"] == 95.0


def test_provider_summary(metrics):
    metrics.record_fetch("soilgrids", 100.0)
    metrics.record_fetch("soilgrids", 200.0)
    metrics.record_error("soilgrids")
    metrics.record_fetch("soilgrids", 0.0, from_cache=True)

    summary = metrics.get_provider_summary("soilgrids")
    assert summary["provider"] == "soilgrids"
    assert summary["latency"]["count"] == 3
    assert summary["cache"]["hits"] == 1
    assert summary["total_errors"] == 1


def test_all_summaries(metrics):
    metrics.record_fetch("soilgrids", 100.0)
    metrics.record_fetch("idena", 50.0)
    summaries = metrics.get_all_summaries()
    assert len(summaries) == 2
    names = [s["provider"] for s in summaries]
    assert names == ["idena", "soilgrids"]


def test_reset(metrics):
    metrics.record_fetch("soilgrids", 100.0)
    metrics.record_error("soilgrids")
    metrics.reset()
    assert metrics.get_latency_stats("soilgrids")["count"] == 0
    assert metrics.get_error_rate("soilgrids") == 0.0
