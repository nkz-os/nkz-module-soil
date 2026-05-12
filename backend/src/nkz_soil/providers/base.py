from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Protocol
from nkz_soil.models.domain import SoilProperty, DepthInterval, SoilDataResult, ProviderHealth, GeographicScope


class SoilDataProvider(Protocol):
    name: str
    priority: int
    geographic_scope: GeographicScope
    update_cadence: timedelta

    async def covers(self, geometry: dict) -> bool: ...
    async def fetch(self, geometry: dict, properties: list[SoilProperty], depths: list[DepthInterval]) -> SoilDataResult: ...
    async def health(self) -> ProviderHealth: ...


class CircuitBreaker:
    def __init__(self, max_failures: int = 5, isolate_seconds: int = 900):
        self.max_failures = max_failures
        self.isolate_seconds = isolate_seconds
        self._failures: dict[str, int] = {}
        self._isolated_until: dict[str, datetime] = {}

    def record_success(self, provider_name: str) -> None:
        self._failures.pop(provider_name, None)
        self._isolated_until.pop(provider_name, None)

    def record_failure(self, provider_name: str) -> None:
        current = self._failures.get(provider_name, 0) + 1
        self._failures[provider_name] = current
        if current >= self.max_failures:
            self._isolated_until[provider_name] = datetime.now() + timedelta(seconds=self.isolate_seconds)

    def is_open(self, provider_name: str) -> bool:
        isolated_until = self._isolated_until.get(provider_name)
        if isolated_until and datetime.now() < isolated_until:
            return True
        if isolated_until and datetime.now() >= isolated_until:
            self._failures.pop(provider_name, None)
            self._isolated_until.pop(provider_name, None)
        return False


class ProviderRegistry:
    def __init__(self):
        self._providers: list[SoilDataProvider] = []

    def register(self, provider: SoilDataProvider) -> None:
        self._providers.append(provider)
        self._providers.sort(key=lambda p: p.priority, reverse=True)

    def get_all(self) -> list[SoilDataProvider]:
        return self._providers
