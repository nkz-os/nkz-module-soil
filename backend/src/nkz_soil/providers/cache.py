import hashlib
import json
import time
from typing import Any

import redis.asyncio as aioredis

from nkz_soil.config import REDIS_URL, CACHE_TTL_BASELINE, CACHE_TTL_REVISABLE
from nkz_soil.models.domain import SoilProperty, DepthInterval, SoilDataResult


CACHE_KEY_PREFIX = "soil:cache:"


def _compute_cache_key(
    provider_name: str,
    geometry: dict,
    properties: list[SoilProperty],
    depths: list[DepthInterval],
) -> str:
    geo_hash = hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()[:16]
    props_hash = hashlib.sha256(",".join(sorted(p.value for p in properties)).encode()).hexdigest()[:8]
    depths_hash = hashlib.sha256(",".join(f"{d.depth_from}-{d.depth_to}" for d in depths).encode()).hexdigest()[:8]
    return f"{CACHE_KEY_PREFIX}{provider_name}:{geo_hash}:{props_hash}:{depths_hash}"


def _get_ttl(provider_name: str, base_ttl: int = CACHE_TTL_BASELINE, revisable_ttl: int = CACHE_TTL_REVISABLE) -> int:
    if provider_name in ("idena", "igme", "bgs"):
        return revisable_ttl
    return base_ttl


def _serialize_result(result: SoilDataResult) -> dict[str, Any]:
    return {
        "provider": result.provider,
        "horizons": [
            {
                "depth_from": h.depth_from,
                "depth_to": h.depth_to,
                "sand": h.sand,
                "silt": h.silt,
                "clay": h.clay,
                "organic_carbon": h.organic_carbon,
                "bulk_density": h.bulk_density,
                "ph": h.ph,
                "cec": h.cec,
                "coarse_fragments": h.coarse_fragments,
                "ksat_saturated": h.ksat_saturated,
                "available_water_capacity": h.available_water_capacity,
                "hydrologic_group": h.hydrologic_group,
                "penetration_resistance": h.penetration_resistance,
            }
            for h in result.horizons
        ],
        "uncertainty": result.uncertainty,
        "geometry": result.geometry,
        "attribution": result.attribution,
        "license": result.license,
        "redistributable": result.redistributable,
        "priority": result.priority,
    }


def _deserialize_result(data: dict[str, Any]) -> SoilDataResult:
    from nkz_soil.models.domain import Horizon

    horizons = [
        Horizon(
            depth_from=h["depth_from"],
            depth_to=h["depth_to"],
            sand=h.get("sand"),
            silt=h.get("silt"),
            clay=h.get("clay"),
            organic_carbon=h.get("organic_carbon"),
            bulk_density=h.get("bulk_density"),
            ph=h.get("ph"),
            cec=h.get("cec"),
            coarse_fragments=h.get("coarse_fragments"),
            ksat_saturated=h.get("ksat_saturated"),
            available_water_capacity=h.get("available_water_capacity"),
            hydrologic_group=h.get("hydrologic_group"),
            penetration_resistance=h.get("penetration_resistance"),
        )
        for h in data["horizons"]
    ]
    return SoilDataResult(
        provider=data["provider"],
        horizons=horizons,
        uncertainty=data["uncertainty"],
        geometry=data["geometry"],
        attribution=data.get("attribution"),
        license=data.get("license"),
        redistributable=data.get("redistributable", True),
        priority=data.get("priority", 0),
    )


class ProviderCache:
    """Redis-backed cache with in-memory fallback for provider fetch results."""

    def __init__(
        self,
        redis_url: str = REDIS_URL,
        base_ttl: int = CACHE_TTL_BASELINE,
        revisable_ttl: int = CACHE_TTL_REVISABLE,
    ):
        self._redis_url = redis_url
        self._base_ttl = base_ttl
        self._revisable_ttl = revisable_ttl
        self._client: aioredis.Redis | None = None
        self._memory_cache: dict[str, tuple[float, dict]] = {}
        self._hits = 0
        self._misses = 0

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def get(
        self,
        provider_name: str,
        geometry: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult | None:
        key = _compute_cache_key(provider_name, geometry, properties, depths)

        mem_entry = self._memory_cache.get(key)
        if mem_entry:
            expiry, data = mem_entry
            if time.time() < expiry:
                self._hits += 1
                return _deserialize_result(data)
            else:
                del self._memory_cache[key]

        try:
            client = await self._get_client()
            raw = await client.get(key)
            if raw:
                data = json.loads(raw)
                ttl = _get_ttl(provider_name, self._base_ttl, self._revisable_ttl)
                self._memory_cache[key] = (time.time() + ttl, data)
                self._hits += 1
                return _deserialize_result(data)
        except Exception:
            pass

        self._misses += 1
        return None

    async def set(
        self,
        provider_name: str,
        geometry: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
        result: SoilDataResult,
    ) -> None:
        key = _compute_cache_key(provider_name, geometry, properties, depths)
        data = _serialize_result(result)
        ttl = _get_ttl(provider_name, self._base_ttl, self._revisable_ttl)

        try:
            client = await self._get_client()
            await client.set(key, json.dumps(data), ex=ttl)
        except Exception:
            pass

        self._memory_cache[key] = (time.time() + ttl, data)

    async def invalidate(self, provider_name: str | None = None) -> None:
        try:
            client = await self._get_client()
            if provider_name:
                pattern = f"{CACHE_KEY_PREFIX}{provider_name}:*"
                async for key in client.scan_iter(match=pattern):
                    await client.delete(key)
            else:
                async for key in client.scan_iter(match=f"{CACHE_KEY_PREFIX}*"):
                    await client.delete(key)
        except Exception:
            pass
        self._memory_cache.clear()

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def stats(self) -> dict[str, int | float]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
            "memory_entries": len(self._memory_cache),
        }

    async def close(self) -> None:
        if self._client:
            await self._client.close()
