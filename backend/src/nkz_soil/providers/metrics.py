import time
from collections import defaultdict
from typing import Any


class ProviderMetrics:
    """Prometheus-style metrics collector per provider."""

    def __init__(self):
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._errors: dict[str, int] = defaultdict(int)
        self._cache_hits: dict[str, int] = defaultdict(int)
        self._cache_misses: dict[str, int] = defaultdict(int)
        self._fetches: dict[str, int] = defaultdict(int)

    def record_fetch(self, provider_name: str, duration_ms: float, from_cache: bool = False) -> None:
        self._latencies[provider_name].append(duration_ms)
        self._fetches[provider_name] += 1
        if from_cache:
            self._cache_hits[provider_name] += 1
        else:
            self._cache_misses[provider_name] += 1

    def record_error(self, provider_name: str) -> None:
        self._errors[provider_name] += 1

    def get_latency_stats(self, provider_name: str) -> dict[str, float]:
        latencies = self._latencies.get(provider_name, [])
        if not latencies:
            return {"min": 0.0, "max": 0.0, "avg": 0.0, "p95": 0.0, "count": 0}
        sorted_lat = sorted(latencies)
        p95_idx = int(len(sorted_lat) * 0.95)
        return {
            "min": min(latencies),
            "max": max(latencies),
            "avg": sum(latencies) / len(latencies),
            "p95": sorted_lat[min(p95_idx, len(sorted_lat) - 1)],
            "count": len(latencies),
        }

    def get_error_rate(self, provider_name: str) -> float:
        total = self._fetches.get(provider_name, 0) + self._errors.get(provider_name, 0)
        if total == 0:
            return 0.0
        return self._errors.get(provider_name, 0) / total

    def get_cache_stats(self, provider_name: str) -> dict[str, int | float]:
        hits = self._cache_hits.get(provider_name, 0)
        misses = self._cache_misses.get(provider_name, 0)
        total = hits + misses
        return {
            "hits": hits,
            "misses": misses,
            "hit_rate": hits / total if total > 0 else 0.0,
        }

    def get_provider_summary(self, provider_name: str) -> dict[str, Any]:
        return {
            "provider": provider_name,
            "latency": self.get_latency_stats(provider_name),
            "error_rate": self.get_error_rate(provider_name),
            "cache": self.get_cache_stats(provider_name),
            "total_fetches": self._fetches.get(provider_name, 0),
            "total_errors": self._errors.get(provider_name, 0),
        }

    def get_all_summaries(self) -> list[dict[str, Any]]:
        all_providers = set(
            list(self._latencies.keys())
            + list(self._errors.keys())
            + list(self._cache_hits.keys())
        )
        return [self.get_provider_summary(p) for p in sorted(all_providers)]

    def reset(self) -> None:
        self._latencies.clear()
        self._errors.clear()
        self._cache_hits.clear()
        self._cache_misses.clear()
        self._fetches.clear()


metrics = ProviderMetrics()
