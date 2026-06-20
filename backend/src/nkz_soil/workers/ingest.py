from __future__ import annotations

import os
import time
from dataclasses import dataclass

from arq.connections import RedisSettings
from arq.cron import CronJob

from nkz_soil.config import REDIS_URL
from nkz_soil.workers.water_budget import compute_water_budgets
from nkz_soil.models.domain import DepthInterval, SoilDataResult, SoilProperty
from nkz_soil.models.ngsi_ld import AgriSoilExtended, GeoProperty, Relationship, TaggedProperty
from nkz_soil.pedotransfer.awc import awc_from_horizons
from nkz_soil.pedotransfer.relative_compaction import relative_compaction
from nkz_soil.pedotransfer.compaction_susceptibility import compaction_susceptibility_score
from nkz_soil.pedotransfer.saxton_rawls import saxton_rawls_2006
from nkz_soil.pedotransfer.scs_groups import scs_hydrologic_group
from nkz_soil.pedotransfer.usda_texture import usda_texture_class
from nkz_soil.providers.base import ProviderRegistry, ProviderResult, RedisCircuitBreaker
from nkz_soil.providers.bgs import BgsProvider
from nkz_soil.providers.cache import ProviderCache
from nkz_soil.providers.esdb_raster import EsdbRasterProvider
from nkz_soil.providers.eu_soil_hydro import EuSoilHydroGridsProvider
from nkz_soil.providers.idena import IdenaProvider
from nkz_soil.providers.igme import IgmeProvider
from nkz_soil.providers.iot_sensor import IotSensorProvider
from nkz_soil.providers.lab_analysis import LabAnalysisProvider
from nkz_soil.providers.lucas import LucasProvider
from nkz_soil.providers.lucas_texture_raster import LucasTextureRasterProvider
from nkz_soil.providers.metrics import metrics
from nkz_soil.providers.soilgrids import SoilGridsProvider
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
    field_capacity: float | None = None
    wilting_point: float | None = None
    usda_texture_class: str | None = None
    hydrologic_group: str | None = None
    penetration_resistance: float | None = None
    relative_compaction: dict | None = None
    compaction_susceptibility: dict | None = None
    emit: dict = None          # redistributable-safe raw values for serialization
    provenance: dict = None    # attr -> {source, license, redistributable}


def _winner_source_per_attr(merged_attrs: dict, results: list[ProviderResult]) -> dict[str, dict]:
    """For each attribute key, find the highest-priority ProviderResult that supplied it."""
    winners: dict[str, dict] = {}
    sorted_results = sorted(results, key=lambda r: -r.priority)
    for attr in merged_attrs:
        for r in sorted_results:
            if attr in r.attributes:
                winners[attr] = {
                    "source_tag": r.source_tag,
                    "license": r.license,
                    "observed_at": r.observed_at,
                    "confidence": r.confidence_interval.get(attr) if r.confidence_interval else None,
                }
                break
    return winners


def build_agri_soil_extended(
    parcel_id: str,
    location: dict,
    merged_horizons: list[dict],
    results: list[ProviderResult],
    parcel_version: str,
) -> AgriSoilExtended:
    """Build an AgriSoilExtended entity tagging horizons with winner-takes-provenance."""
    winners = _winner_source_per_attr({"horizons": True}, results)
    hw = winners.get("horizons", {})
    return AgriSoilExtended(
        id=f"urn:ngsi-ld:AgriSoilExtended:{parcel_id}",
        location=GeoProperty(value=location),
        hasAgriParcel=Relationship(object=f"urn:ngsi-ld:AgriParcel:{parcel_id}"),
        horizons=TaggedProperty(
            value=merged_horizons,
            provided_by=hw.get("source_tag"),
            license_id=hw.get("license"),
            observed_at=hw.get("observed_at"),
        ),
        parcelVersionId=TaggedProperty(value=parcel_version),
    )


async def startup(ctx: dict) -> None:
    registry = ProviderRegistry()
    for provider in (
        LabAnalysisProvider(), IotSensorProvider(), IdenaProvider(), IgmeProvider(),
        BgsProvider(), LucasProvider(), LucasTextureRasterProvider(), EsdbRasterProvider(),
        EuSoilHydroGridsProvider(), SoilGridsProvider(),
    ):
        registry.register(provider)
    ctx["registry"] = registry
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
    from nkz_soil.storage.orion import set_current_tenant
    set_current_tenant(tenant_id)

    registry: ProviderRegistry = ctx["registry"]
    circuit_breaker: RedisCircuitBreaker = ctx["circuit_breaker"]
    cache: ProviderCache = ctx["cache"]

    # Geometry self-heal: the manual /ingest path enqueues an empty geometry.
    # Resolve the parcel's footprint from Orion-LD so providers have something to sample.
    if not geometry:
        async with OrionClient(tenant_id) as orion:
            parcels = await orion.query_entities(type="AgriParcel")
            match = [e for e in parcels if e.get("id", "").endswith(parcel_id)]
            if match:
                geometry = match[0].get("location", {}).get("value", {})
        if not geometry:
            return {"status": "skipped", "reason": "no_geometry", "parcelId": parcel_id}

    all_results = []
    provider_results: list[ProviderResult] = []
    for provider in registry.get_all():
        if await circuit_breaker.is_open(provider.name):
            continue
        if not provider.covers(geometry):
            continue

        cached = await cache.get(provider.name, geometry, ALL_PROPERTIES, STANDARD_DEPTHS)
        if cached:
            # The registry is the authority on cascade priority; stamp it onto
            # the result so _cascade_merge can sort by result.priority.
            if isinstance(cached, SoilDataResult):
                cached.priority = provider.priority
            all_results.append(cached)
            if isinstance(cached, ProviderResult):
                provider_results.append(cached)
            await circuit_breaker.record_success(provider.name)
            metrics.record_fetch(provider.name, 0.0, from_cache=True)
            continue

        try:
            start = time.monotonic()
            result = await provider.fetch(geometry, ALL_PROPERTIES, STANDARD_DEPTHS)
            duration_ms = (time.monotonic() - start) * 1000
            if isinstance(result, SoilDataResult):
                result.priority = provider.priority
            all_results.append(result)
            if isinstance(result, ProviderResult):
                provider_results.append(result)
            await cache.set(provider.name, geometry, ALL_PROPERTIES, STANDARD_DEPTHS, result)
            await circuit_breaker.record_success(provider.name)
            metrics.record_fetch(provider.name, duration_ms, from_cache=False)
        except Exception:
            await circuit_breaker.record_failure(provider.name)
            metrics.record_error(provider.name)
            continue

    merged_horizons = _cascade_merge(all_results, STANDARD_DEPTHS)
    merged_horizons = _apply_pedotransfer(merged_horizons)

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

    # Synthesize ProviderResult for provenance tracking from legacy SoilDataResult providers.
    # Each legacy result contributes a horizons-keyed entry so the winner election has coverage.
    legacy_as_provider_results = [
        ProviderResult(
            priority=PROVIDER_PRIORITIES.get(r.provider, 0),
            attributes={"horizons": True},
            source_tag=r.provider,
            license=r.attribution or "unknown",
        )
        for r in all_results
        if not isinstance(r, ProviderResult) and hasattr(r, "provider")
    ]
    all_provider_results = provider_results + legacy_as_provider_results

    entity = build_agri_soil_extended(
        parcel_id=f"{tenant_id}:{parcel_id}",
        location=geometry,
        merged_horizons=[_horizon_to_dict(h) for h in merged_horizons],
        results=all_provider_results,
        parcel_version=parcel_version_id,
    ).to_ngsi()

    if compaction_list:
        entity["relativeCompaction"] = {"type": "Property", "value": compaction_list}

    # Aggregate compaction susceptibility across all horizons
    susc_horizons = [
        h.compaction_susceptibility
        for h in merged_horizons
        if h.compaction_susceptibility
    ]
    if susc_horizons:
        scores = [s["score"] for s in susc_horizons]
        avg_score = round(sum(scores) / len(scores))
        worst = max(susc_horizons, key=lambda s: s["score"])
        entity["compactionSusceptibility"] = {
            "type": "Property",
            "value": {
                "overallScore": avg_score,
                "overallClass": worst["class"],
                "worstHorizonScore": worst["score"],
                "worstHorizonClass": worst["class"],
            },
        }

    entity_id = entity["id"]
    async with OrionClient(tenant_id) as orion:
        existing = await orion.query_entities(type="AgriSoilExtended")
        existing_match = [e for e in existing if e.get("id") == entity_id]

        if existing_match:
            await orion.patch_entity(entity_id, {
                k: v for k, v in entity.items()
                if k not in ("id", "type", "@context")
            })
        else:
            await orion.create_entity(entity)

    return {"status": "ingested", "parcelId": parcel_id, "horizons": len(merged_horizons)}


_MERGE_ATTRS = ["sand", "silt", "clay", "organic_carbon", "bulk_density",
                "ph", "cec", "coarse_fragments", "penetration_resistance"]


def _cascade_merge(results: list, depths: list[DepthInterval]) -> list[EnrichedHorizon]:
    merged: dict[str, dict] = {f"{d.depth_from}-{d.depth_to}": {} for d in depths}
    emit: dict[str, dict] = {k: {} for k in merged}
    prov: dict[str, dict] = {k: {} for k in merged}

    # Only SoilDataResult-shaped results participate (have .horizons + .priority).
    sdr = [r for r in results if hasattr(r, "horizons") and hasattr(r, "priority")]
    for result in sorted(sdr, key=lambda r: r.priority, reverse=True):
        redistributable = getattr(result, "redistributable", True)
        for horizon in result.horizons:
            key = f"{horizon.depth_from}-{horizon.depth_to}"
            if key not in merged:
                continue
            for attr in _MERGE_ATTRS:
                val = getattr(horizon, attr, None)
                if val is None:
                    continue
                if attr not in merged[key]:           # highest-priority winner (PTF input)
                    merged[key][attr] = val
                    prov[key][attr] = {"source": result.provider, "license": result.license,
                                       "redistributable": redistributable}
                if redistributable and attr not in emit[key]:   # best redistributable (emit)
                    emit[key][attr] = val

    out = []
    for k, vals in merged.items():
        df, dt = (int(x) for x in k.split("-"))
        out.append(EnrichedHorizon(depth_from=df, depth_to=dt, emit=emit[k],
                                   provenance=prov[k], **vals))
    return out


def _apply_pedotransfer(horizons: list[EnrichedHorizon]) -> list[EnrichedHorizon]:
    for h in horizons:
        if h.sand is not None and h.clay is not None and h.organic_carbon is not None:
            ptf = saxton_rawls_2006(h.sand, h.clay, h.organic_carbon)
            h.ksat_saturated = ptf["ksat"]
            h.available_water_capacity = awc_from_horizons(
                ptf["field_capacity"], ptf["wilting_point"]
            )
            h.field_capacity = ptf["field_capacity"]
            h.wilting_point = ptf["wilting_point"]
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

        if h.sand is not None and h.silt is not None and h.clay is not None:
            h.usda_texture_class = usda_texture_class(h.sand, h.silt, h.clay)

        # Compaction susceptibility (texture-based inherent risk)
        if h.usda_texture_class is not None:
            om_pct = None
            if h.organic_carbon is not None:
                om_pct = h.organic_carbon * 1.724  # van Bemmelen factor
            bd_ref = None
            if (
                h.bulk_density is not None
                and h.sand is not None
                and h.silt is not None
                and h.clay is not None
            ):
                from nkz_soil.pedotransfer.relative_compaction import (
                    textural_class,
                    REFERENCE_BULK_DENSITY,
                )
                tex = textural_class(h.sand, h.silt, h.clay)
                bd_ref = REFERENCE_BULK_DENSITY.get(tex)
            h.compaction_susceptibility = compaction_susceptibility_score(
                usda_texture=h.usda_texture_class,
                organic_matter_pct=om_pct,
                coarse_fragments_pct=h.coarse_fragments,
                bulk_density=h.bulk_density,
                bulk_density_ref=bd_ref,
            )

    return horizons


def _emit_raw(h: EnrichedHorizon, attr: str):
    """Emit the redistributable-safe value: only if a redistributable source supplied it.

    License boundary: a raw fraction whose only/winning source is non-redistributable
    (e.g. JRC LUCAS texture) is withheld here, even though it was used for pedotransfer.
    """
    if h.emit is not None and attr in h.emit:
        return h.emit[attr]
    # No provenance recorded (e.g. direct lab input) -> treat as emittable.
    if h.provenance is None or attr not in h.provenance:
        return getattr(h, attr, None)
    return None


def _horizon_to_dict(horizon: EnrichedHorizon) -> dict:
    return {
        "depthFrom": horizon.depth_from,
        "depthTo": horizon.depth_to,
        "sand": _emit_raw(horizon, "sand"),
        "silt": _emit_raw(horizon, "silt"),
        "clay": _emit_raw(horizon, "clay"),
        "organicCarbon": _emit_raw(horizon, "organic_carbon"),
        "bulkDensity": _emit_raw(horizon, "bulk_density"),
        "ph": _emit_raw(horizon, "ph"),
        "cec": _emit_raw(horizon, "cec"),
        "coarseFragments": _emit_raw(horizon, "coarse_fragments"),
        "penetrationResistance": _emit_raw(horizon, "penetration_resistance"),
        # Derived products — always emitted (new works under the license).
        "ksatSaturated": horizon.ksat_saturated,
        "availableWaterCapacity": horizon.available_water_capacity,
        "fieldCapacity": horizon.field_capacity,
        "wiltingPoint": horizon.wilting_point,
        "hydrologicGroup": horizon.hydrologic_group,
        "usdaTextureClass": horizon.usda_texture_class,
        "compactionSusceptibility": (
            {
                "score": horizon.compaction_susceptibility["score"],
                "class": horizon.compaction_susceptibility["class"],
                "texturalScore": horizon.compaction_susceptibility["textural_score"],
                "modifiersApplied": horizon.compaction_susceptibility["modifiers_applied"],
                "indicativeElevatedBd": horizon.compaction_susceptibility["indicative_elevated_bd"],
            }
            if horizon.compaction_susceptibility
            else None
        ),
        # Flat fields for GeoJSON layer consumption (continuous + categorical)
        "compactionSusceptibilityScore": (
            horizon.compaction_susceptibility["score"]
            if horizon.compaction_susceptibility
            else None
        ),
        "compactionSusceptibilityClass": (
            horizon.compaction_susceptibility["class"]
            if horizon.compaction_susceptibility
            else None
        ),
    }


def _primary_source(results: list) -> str:
    if not results:
        return "soilgrids"
    return max(results, key=lambda r: PROVIDER_PRIORITIES.get(r.provider, 0)).provider


def _aggregate_uncertainty(results: list) -> float:
    if not results:
        return 0.5
    return round(sum(r.uncertainty for r in results) / len(results), 2)


async def backfill_parcels_without_soil(ctx: dict) -> None:
    """Cada 6h: detecta parcelas sin AgriSoilExtended y las ingiere."""
    import asyncpg
    import logging
    from uuid import uuid4
    from arq.connections import ArqRedis

    logger = logging.getLogger(__name__)
    logger.info("Backfill soil: scanning for parcels without soil data")

    db_url = os.environ.get("SOIL_PG_DSN", "")
    if not db_url:
        db_url = os.environ.get("POSTGRES_URL", "")

    # Discover tenants: try DB first, then env var, then guess from Orion
    tenants = []
    if db_url:
        try:
            conn = await asyncpg.connect(db_url)
            rows = await conn.fetch(
                "SELECT tenant_id FROM tenant_installed_modules "
                "WHERE module_id='soil' AND is_enabled=true"
            )
            await conn.close()
            tenants = [r["tenant_id"] for r in rows]
        except Exception as e:
            logger.warning("Backfill soil: DB query failed (%s), falling back to env", e)

    if not tenants:
        env_tenants = os.environ.get("SOIL_ENABLED_TENANTS", "")
        if env_tenants:
            tenants = [t.strip() for t in env_tenants.split(",") if t.strip()]
            logger.info("Backfill soil: using SOIL_ENABLED_TENANTS=%s", tenants)

    if not tenants:
        # Last resort: scan known tenants from Orion
        from nkz_soil.storage.orion import OrionClient
        for guess in ("montiko", "asociacion-allotarra", "platform"):
            try:
                async with OrionClient(guess) as orion:
                    parcels = await orion.query_entities(type="AgriParcel")
                    if parcels:
                        tenants.append(guess)
            except Exception:
                pass
        logger.info("Backfill soil: discovered tenants from Orion: %s", tenants)
    logger.info("Backfill soil: %d tenants with soil module enabled", len(tenants))

    redis: ArqRedis = ctx.get("redis")  # type: ignore[assignment]
    if redis is None:
        redis = ArqRedis.from_url(REDIS_URL)

    total_enqueued = 0
    for tenant_id in tenants:
        try:
            async with OrionClient(tenant_id) as orion:
                parcels = await orion.query_entities(type="AgriParcel")
                soils = await orion.query_entities(type="AgriSoilExtended")

            soiled = set()
            for s in soils:
                ref = s.get("hasAgriParcel") or {}
                obj = ref.get("object") if isinstance(ref, dict) else ref
                if obj:
                    soiled.add(obj)

            enqueued = 0
            for p in parcels:
                pid = p.get("id", "")
                if pid and pid not in soiled:
                    parcel_short = pid.split(":")[-1]
                    geometry = p.get("location", {}).get("value", {})
                    await redis.enqueue_job(
                        "ingest_parcel",
                        parcel_short,
                        tenant_id,
                        geometry,
                        "v1",
                    )
                    enqueued += 1

            if enqueued:
                logger.info(
                    "Backfill soil: enqueued %d parcels for %s",
                    enqueued, tenant_id,
                )
            total_enqueued += enqueued

        except Exception as e:
            logger.error("Backfill soil: error processing %s (%s)", tenant_id, e)

    logger.info("Backfill soil: done — %d total parcels enqueued", total_enqueued)

    if ctx.get("redis") is None:
        await redis.close()


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
    functions = [ingest_parcel, compute_water_budgets, backfill_parcels_without_soil]
    cron_jobs = [
        CronJob(
            name="backfill_soil",
            coroutine=backfill_parcels_without_soil,
            month=None,
            day=None,
            weekday=None,
            hour={0, 6, 12, 18},
            minute=0,
            second=0,
            microsecond=0,
            run_at_startup=True,
            unique=True,
            job_id="backfill_soil",
            timeout_s=600,
            keep_result_s=3600,
            keep_result_forever=False,
            max_tries=1,
        ),
        CronJob(
            name="reap_stuck_jobs",
            coroutine=reap_stuck_jobs,
            month=None,
            day=None,
            weekday=None,
            hour=1,
            minute=0,
            second=0,
            microsecond=0,
            run_at_startup=False,
            unique=True,
            job_id="reap_stuck_jobs",
            timeout_s=300,
            keep_result_s=3600,
            keep_result_forever=False,
            max_tries=3,
        ),
        CronJob(
            name="compute_water_budgets",
            coroutine=compute_water_budgets,
            month=None,
            day=None,
            weekday=None,
            hour={0, 6, 12, 18},
            minute=0,
            second=0,
            microsecond=0,
            run_at_startup=False,
            unique=True,
            job_id="compute_water_budgets",
            timeout_s=600,
            keep_result_s=3600,
            keep_result_forever=False,
            max_tries=1,
        ),
    ]
    redis_settings = _parse_redis_url(REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
