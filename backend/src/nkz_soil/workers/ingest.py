from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from arq.connections import RedisSettings

from nkz_soil.config import CONTEXT_URL, REDIS_URL
from nkz_soil.models.domain import DepthInterval, SoilProperty
from nkz_soil.pedotransfer.awc import awc_from_horizons
from nkz_soil.pedotransfer.relative_compaction import relative_compaction
from nkz_soil.pedotransfer.saxton_rawls import saxton_rawls_2006
from nkz_soil.pedotransfer.scs_groups import scs_hydrologic_group
from nkz_soil.providers.base import ProviderRegistry, RedisCircuitBreaker
from nkz_soil.providers.cache import ProviderCache
from nkz_soil.providers.metrics import metrics
from nkz_soil.storage.orion import OrionClient

STANDARD_DEPTHS = [
    DepthInterval(0, 5),
    DepthInterval(5, 15),
    DepthInterval(15, 30),
    DepthInterval(30, 60),
    DepthInterval(60, 100),
]

STANDARD_PROPERTIES = [
    SoilProperty.SAND,
    SoilProperty.SILT,
    SoilProperty.CLAY,
    SoilProperty.ORGANIC_CARBON,
    SoilProperty.BULK_DENSITY,
    SoilProperty.PH,
    SoilProperty.CEC,
    SoilProperty.COARSE_FRAGMENTS,
]

ALL_PROPERTIES = STANDARD_PROPERTIES + [
    SoilProperty.KSAT_SATURATED,
    SoilProperty.AVAILABLE_WATER_CAPACITY,
    SoilProperty.HYDROLOGIC_GROUP,
    SoilProperty.PENETRATION_RESISTANCE,
]

PROVIDER_PRIORITIES = {
    "lab_analysis": 100,
    "iot_sensor": 90,
    "idena": 40,
    "igme": 30,
    "bgs": 30,
    "lucas": 25,
    "eu_soil_hydro": 20,
    "soilgrids": 10,
}


@dataclass
class EnrichedHorizon:
    depth_from: int
    depth_to: int
    sand: float | None = None
    silt: float | None = None
    clay: float | None = None
    organic_carbon: float | None = None
    bulk_density: float | None = None
    ph: float | None = None
    cec: float | None = None
    coarse_fragments: float | None = None
    ksat_saturated: float | None = None
    available_water_capacity: float | None = None
    hydrologic_group: str | None = None
    penetration_resistance: float | None = None
    relative_compaction: dict | None = None


async def startup(ctx: dict) -> None:
    ctx["registry"] = ProviderRegistry()
    ctx["circuit_breaker"] = RedisCircuitBreaker(redis_url=REDIS_URL)
    ctx["cache"] = ProviderCache(redis_url=REDIS_URL)


async def shutdown(ctx: dict) -> None:
    cb: RedisCircuitBreaker | None = ctx.get("circuit_breaker")
    if cb:
        await cb.close()
    cache: ProviderCache | None = ctx.get("cache")
    if cache:
        await cache.close()


async def ingest_parcel(
    ctx: dict,
    parcel_id: str,
    tenant_id: str,
    geometry: dict,
    parcel_version_id: str,
) -> dict:
    registry: ProviderRegistry = ctx["registry"]
    circuit_breaker: RedisCircuitBreaker = ctx["circuit_breaker"]
    cache: ProviderCache = ctx["cache"]

    all_results = []
    for provider in registry.get_all():
        if await circuit_breaker.is_open(provider.name):
            continue
        if not provider.covers(geometry):
            continue

        cached = await cache.get(provider.name, geometry, ALL_PROPERTIES, STANDARD_DEPTHS)
        if cached:
            all_results.append(cached)
            await circuit_breaker.record_success(provider.name)
            metrics.record_fetch(provider.name, 0.0, from_cache=True)
            continue

        try:
            start = time.monotonic()
            result = await provider.fetch(geometry, ALL_PROPERTIES, STANDARD_DEPTHS)
            duration_ms = (time.monotonic() - start) * 1000
            all_results.append(result)
            await cache.set(provider.name, geometry, ALL_PROPERTIES, STANDARD_DEPTHS, result)
            await circuit_breaker.record_success(provider.name)
            metrics.record_fetch(provider.name, duration_ms, from_cache=False)
        except Exception:
            await circuit_breaker.record_failure(provider.name)
            metrics.record_error(provider.name)
            continue

    merged_horizons = _cascade_merge(all_results, STANDARD_DEPTHS)
    merged_horizons = _apply_pedotransfer(merged_horizons)
    uncertainty = _aggregate_uncertainty(all_results)
    now_iso = datetime.now(timezone.utc).isoformat()

    compaction_list = [
        {
            "depthFrom": h.depth_from,
            "depthTo": h.depth_to,
            "value": h.relative_compaction["value"],
            "classification": h.relative_compaction["classification"],
        }
        for h in merged_horizons
        if h.relative_compaction
    ]

    async with OrionClient(tenant_id) as orion:
        entity_id = f"urn:ngsi-ld:AgriSoil:{tenant_id}:{parcel_id}"
        existing = await orion.query_entities(type="AgriSoil")
        existing_match = [
            e for e in existing
            if e.get("id") == entity_id
        ]

        entity: dict = {
            "id": entity_id,
            "type": "AgriSoil",
            "@context": [CONTEXT_URL],
            "location": {"type": "GeoProperty", "value": geometry},
            "refAgriParcel": {
                "type": "Relationship",
                "object": f"urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}",
            },
            "parcelVersionId": {"type": "Property", "value": parcel_version_id},
            "horizons": {
                "type": "Property",
                "value": [_horizon_to_dict(h) for h in merged_horizons],
            },
            "dataSource": {"type": "Property", "value": _primary_source(all_results)},
            "uncertainty": {"type": "Property", "value": uncertainty},
            "lastUpdated": {"type": "Property", "value": now_iso},
        }
        if compaction_list:
            entity["relativeCompaction"] = {
                "type": "Property",
                "value": compaction_list,
            }

        if existing_match:
            await orion.patch_entity(entity_id, {
                k: v for k, v in entity.items()
                if k not in ("id", "type", "@context")
            })
        else:
            await orion.create_entity(entity)

    return {"status": "ingested", "parcelId": parcel_id, "horizons": len(merged_horizons)}


def _cascade_merge(results: list, depths: list[DepthInterval]) -> list[EnrichedHorizon]:
    merged: dict[str, dict] = {f"{d.depth_from}-{d.depth_to}": {} for d in depths}
    for result in sorted(
        results, key=lambda r: PROVIDER_PRIORITIES.get(r.provider, 0), reverse=True
    ):
        for horizon in result.horizons:
            key = f"{horizon.depth_from}-{horizon.depth_to}"
            if key in merged:
                for attr in [
                    "sand", "silt", "clay", "organic_carbon", "bulk_density",
                    "ph", "cec", "coarse_fragments", "penetration_resistance",
                ]:
                    val = getattr(horizon, attr, None)
                    if val is not None and attr not in merged[key]:
                        merged[key][attr] = val
    return [
        EnrichedHorizon(depth_from=int(k.split("-")[0]), depth_to=int(k.split("-")[1]), **v)
        for k, v in merged.items()
    ]


def _apply_pedotransfer(horizons: list[EnrichedHorizon]) -> list[EnrichedHorizon]:
    for h in horizons:
        if h.sand is not None and h.clay is not None and h.organic_carbon is not None:
            ptf = saxton_rawls_2006(h.sand, h.clay, h.organic_carbon)
            h.ksat_saturated = ptf["ksat"]
            h.available_water_capacity = awc_from_horizons(
                ptf["field_capacity"], ptf["wilting_point"]
            )
            h.hydrologic_group = scs_hydrologic_group(ptf["ksat"])

        if (
            h.bulk_density is not None
            and h.sand is not None
            and h.silt is not None
            and h.clay is not None
        ):
            h.relative_compaction = relative_compaction(
                h.bulk_density, h.sand, h.silt, h.clay
            )

    return horizons


def _horizon_to_dict(horizon: EnrichedHorizon) -> dict:
    return {
        "depthFrom": horizon.depth_from,
        "depthTo": horizon.depth_to,
        "sand": horizon.sand,
        "silt": horizon.silt,
        "clay": horizon.clay,
        "organicCarbon": horizon.organic_carbon,
        "bulkDensity": horizon.bulk_density,
        "ph": horizon.ph,
        "cec": horizon.cec,
        "coarseFragments": horizon.coarse_fragments,
        "ksatSaturated": horizon.ksat_saturated,
        "availableWaterCapacity": horizon.available_water_capacity,
        "hydrologicGroup": horizon.hydrologic_group,
        "penetrationResistance": horizon.penetration_resistance,
    }


def _primary_source(results: list) -> str:
    if not results:
        return "soilgrids"
    return max(results, key=lambda r: PROVIDER_PRIORITIES.get(r.provider, 0)).provider


def _aggregate_uncertainty(results: list) -> float:
    if not results:
        return 0.5
    return round(sum(r.uncertainty for r in results) / len(results), 2)


async def reap_stuck_jobs(ctx: dict) -> None:
    """Detect and clean up stuck ARQ jobs.

    Scans Redis ARQ state keys for jobs that have been in 'running' or
    'pending' state for longer than the timeout threshold. Marks them as
    failed so they don't block the queue indefinitely.
    """
    import logging
    from arq.connections import ArqRedis

    logger = logging.getLogger(__name__)
    timeout_seconds = 1800  # 30 minutes

    redis: ArqRedis = ctx.get("redis")  # type: ignore[assignment]
    if redis is None:
        redis = ArqRedis.from_url(REDIS_URL)

    try:
        # ARQ stores job state in Redis hashes keyed by 'arq:job:{job_id}'.
        # We scan for all keys matching this pattern and check their status.
        cursor = 0
        now = time.monotonic()
        reaped = 0

        while True:
            cursor, keys = await redis.scan(
                cursor=cursor, match="arq:job:*", count=100
            )
            for key in keys:
                job_data = await redis.hgetall(key)
                if not job_data:
                    continue

                job_id = key.split(":")[-1]
                status = job_data.get("status", "")
                enqueue_time = float(job_data.get("enqueue_time", 0))

                # Check if job has been running/pending too long
                age = now - enqueue_time
                if status in ("running", "pending") and age > timeout_seconds:
                    logger.warning(
                        "Reaping stuck job %s (status=%s, age=%.0fs)",
                        job_id, status, age,
                    )
                    await redis.hset(key, mapping={"status": "failed", "error": "stuck_job_timeout"})
                    reaped += 1

            if cursor == 0:
                break

        if reaped > 0:
            logger.info("Reaped %d stuck jobs", reaped)

    except Exception:
        logger.exception("Error in reap_stuck_jobs")
    finally:
        if ctx.get("redis") is None:
            await redis.close()


def _parse_redis_url(url: str) -> RedisSettings:
    """Parse redis://[:password@]host:port/db URL into RedisSettings."""
    url = url.replace("redis://", "").replace("rediss://", "")
    password = None
    # Extract password if present
    if "@" in url:
        auth_part, url = url.split("@", 1)
        if auth_part.startswith(":"):
            password = auth_part[1:]  # :password@host
        elif ":" in auth_part:
            _, password = auth_part.split(":", 1)  # user:password@host
    parts = url.split("/")
    db = 0
    if len(parts) > 1 and parts[1].strip():
        db = int(parts[1])
    host_port = parts[0].split(":")
    host = host_port[0]
    port = int(host_port[1]) if len(host_port) > 1 else 6379
    return RedisSettings(host=host, port=port, database=db, password=password)


class WorkerSettings:
    functions = [ingest_parcel, reap_stuck_jobs]
    redis_settings = _parse_redis_url(REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
