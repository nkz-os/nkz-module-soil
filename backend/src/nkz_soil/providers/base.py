from datetime import datetime, timedelta, timezone
from typing import Protocol

import redis.asyncio as aioredis
from shapely.geometry import box, shape

from nkz_soil.config import REDIS_URL
from nkz_soil.models.domain import SoilProperty, DepthInterval, SoilDataResult, ProviderHealth, GeographicScope


def geometry_intersects_bbox(geometry: dict, bbox: tuple[float, float, float, float]) -> bool:
    """Check if a GeoJSON geometry intersects with a bounding box.

    bbox: (minx, miny, maxx, maxy)
    """
    if bbox == (-180, -90, 180, 90):
        return True
    try:
        geom = shape(geometry)
        bbox_geom = box(*bbox)
        return bool(geom.intersects(bbox_geom))
    except Exception:
        return True


class SoilDataProvider(Protocol):
    name: str
    priority: int
    geographic_scope: GeographicScope
    update_cadence: timedelta

    def covers(self, geometry: dict) -> bool: ...
    async def fetch(self, geometry: dict, properties: list[SoilProperty], depths: list[DepthInterval]) -> SoilDataResult: ...
    async def health(self) -> ProviderHealth: ...


class CircuitBreaker:
    """In-memory circuit breaker (single-process only)."""

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
            self._isolated_until[provider_name] = datetime.now(timezone.utc) + timedelta(seconds=self.isolate_seconds)

    def is_open(self, provider_name: str) -> bool:
        isolated_until = self._isolated_until.get(provider_name)
        if isolated_until and datetime.now(timezone.utc) < isolated_until:
            return True
        if isolated_until and datetime.now(timezone.utc) >= isolated_until:
            self._failures.pop(provider_name, None)
            self._isolated_until.pop(provider_name, None)
        return False


class RedisCircuitBreaker:
    """Redis-backed circuit breaker (shared across replicas)."""

    FAILURE_KEY = "soil:cb:{name}:failures"
    ISOLATED_KEY = "soil:cb:{name}:isolated_until"

    def __init__(
        self,
        redis_url: str = REDIS_URL,
        max_failures: int = 5,
        isolate_seconds: int = 900,
    ):
        self.max_failures = max_failures
        self.isolate_seconds = isolate_seconds
        self._redis_url = redis_url
        self._client: aioredis.Redis | None = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def record_success(self, provider_name: str) -> None:
        client = await self._get_client()
        await client.delete(
            self.FAILURE_KEY.format(name=provider_name),
            self.ISOLATED_KEY.format(name=provider_name),
        )

    async def record_failure(self, provider_name: str) -> None:
        client = await self._get_client()
        key = self.FAILURE_KEY.format(name=provider_name)
        current = await client.incr(key)
        if current >= self.max_failures:
            iso_key = self.ISOLATED_KEY.format(name=provider_name)
            await client.set(iso_key, datetime.now(timezone.utc).isoformat(), ex=self.isolate_seconds)

    async def is_open(self, provider_name: str) -> bool:
        client = await self._get_client()
        iso_key = self.ISOLATED_KEY.format(name=provider_name)
        isolated_until = await client.get(iso_key)
        if isolated_until:
            try:
                until = datetime.fromisoformat(isolated_until)
                if datetime.now(timezone.utc) < until:
                    return True
            except ValueError:
                pass
            await client.delete(iso_key, self.FAILURE_KEY.format(name=provider_name))
        return False

    async def close(self) -> None:
        if self._client:
            await self._client.close()


class ProviderRegistry:
    def __init__(self):
        self._providers: list[SoilDataProvider] = []

    def register(self, provider: SoilDataProvider) -> None:
        self._providers.append(provider)
        self._providers.sort(key=lambda p: p.priority, reverse=True)

    def get_all(self) -> list[SoilDataProvider]:
        return self._providers
