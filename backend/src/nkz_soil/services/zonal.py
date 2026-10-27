"""Soil properties per management-zone geometry.

Resolution chain, first step that resolves INSIDE the zone wins:
  1. SoilSamplingPoint entities inside the zone      -> lab_analysis      zone_specific
  2. SoilDerivedRaster of the parcel, zonal mean     -> derived_raster    zone_specific
  3. IDENA soil-map polygons clipped to the zone     -> idena             zone_specific
     only when the parcel itself spans >= 2 classes or the zone's dominant
     class differs from the parcel's; otherwise the step does not resolve
  4. LUCAS point inside the zone                     -> LUCAS             zone_specific
  5. the parcel's own values                         -> parcel's provider parcel_inherited

A step that raises is logged and skipped, and the result is marked degraded so
it is never cached (a transient outage must not freeze an inherited answer).
"""
from __future__ import annotations

import asyncio
import io
import json
import logging

import redis.asyncio as aioredis
from shapely.geometry import shape

from nkz_soil.config import REDIS_URL
from nkz_soil.providers.idena import TEXTURE_CLASS_FRACTIONS, IdenaProvider
from nkz_soil.providers.lucas import LucasProvider
from nkz_soil.storage.minio import get_minio_client
from nkz_soil.storage.orion import OrionClient
from nkz_soil.util.ngsi import horizons_of

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 7 * 24 * 3600
ZONE_SPECIFIC = "zone_specific"
PARCEL_INHERITED = "parcel_inherited"

_HORIZON_KEYS = (
    "sand", "silt", "clay", "organicCarbon", "fieldCapacity", "wiltingPoint",
    "availableWaterCapacity", "ksatSaturated", "hydrologicGroup", "usdaTextureClass", "ph",
)
_NUMERIC_KEYS = tuple(k for k in _HORIZON_KEYS if k not in ("hydrologicGroup", "usdaTextureClass"))
_CATEGORICAL_KEYS = ("hydrologicGroup", "usdaTextureClass")
# horizon-dict key (camelCase, as stored in AgriSoilExtended) -> EnrichedHorizon field
_SOURCE_FIELDS = (
    ("sand", "sand"), ("silt", "silt"), ("clay", "clay"),
    ("organicCarbon", "organic_carbon"), ("ph", "ph"),
)
_RASTER_PROPS = {
    "sand": "sand", "silt": "silt", "clay": "clay",
    "organiccarbon": "organic_carbon", "ph": "ph",
}


def _short_id(parcel_id: str) -> str:
    return parcel_id.split(":")[-1]


def _parse_depth(depth: str) -> tuple[int, int]:
    lo, hi = depth.split("-")
    return int(lo), int(hi)


def _val(raw):
    if isinstance(raw, dict) and "value" in raw:
        return raw["value"]
    return raw


def _num(raw) -> float | None:
    raw = _val(raw)
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _overlap(h_from, h_to, lo, hi) -> float:
    return max(0.0, min(h_to, hi) - max(h_from, lo))


# --------------------------------------------------------------------- cache

_client: aioredis.Redis | None = None


def _cache_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            REDIS_URL, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )
    return _client


def _cache_key(tenant: str, parcel_id: str, zone: dict, depth: str) -> str:
    return f"soil:zonal:{tenant}:{_short_id(parcel_id)}:{zone['zoneVersion']}:{zone['zoneId']}:{depth}"


async def invalidate_parcel(tenant: str, parcel_id: str, client=None) -> None:
    """Drop every cached zone result of a parcel. Never raises: a cache failure
    must not fail an ingest (entries then expire by TTL)."""
    pattern = f"soil:zonal:{tenant}:{_short_id(parcel_id)}:*"
    try:
        redis = client if client is not None else _cache_client()
        keys = [k async for k in redis.scan_iter(match=pattern)]
        if keys:
            await redis.delete(*keys)
    except Exception:
        logger.warning("zonal cache invalidation failed", extra={"tenant": tenant, "parcel": parcel_id}, exc_info=True)


# ------------------------------------------------------------------- sources

async def _sampling_points_in_zone(tenant: str, geometry: dict) -> list[dict]:
    async with OrionClient(tenant) as orion:
        points = await orion.query_entities(type="SoilSamplingPoint", geometry=geometry)
    zone = shape(geometry)
    inside = []
    for p in points:
        loc = _val(p.get("location"))
        if isinstance(loc, dict) and loc.get("coordinates") and not zone.covers(shape(loc)):
            continue
        inside.append(p)
    return inside


def _read_zonal_mean(s3, uri: str, geometry: dict) -> float | None:
    import numpy as np
    from rasterio.io import MemoryFile
    from rasterio.mask import mask

    bucket, key = uri.replace("s3://", "").split("/", 1)
    data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    with MemoryFile(io.BytesIO(data)) as mem, mem.open() as src:
        try:
            arr, _ = mask(src, [geometry], crop=True, filled=False, all_touched=True)
        except ValueError:  # zone does not overlap the raster
            return None
        vals = np.ma.asarray(arr[0]).compressed().astype("float64")
        vals = vals[np.isfinite(vals)]
        if src.nodata is not None:
            vals = vals[vals != src.nodata]
    return float(vals.mean()) if vals.size else None


async def _raster_values_in_zone(
    tenant: str, parcel_id: str, geometry: dict, depth: tuple[int, int]
) -> dict[str, float] | None:
    short = _short_id(parcel_id)
    async with OrionClient(tenant) as orion:
        entities = await orion.query_entities(type="SoilDerivedRaster")
    s3 = get_minio_client()
    lo, hi = depth
    acc: dict[str, list[tuple[float, float]]] = {}
    for e in entities:
        ref = e.get("hasAgriParcel", {})
        if not str(ref.get("object", "")).endswith(f":{short}"):
            continue
        prop = _RASTER_PROPS.get(str(_val(e.get("soilProperty", e.get("property"))) or "").lower())
        d_from, d_to = _num(e.get("depthFrom")), _num(e.get("depthTo"))
        uri = _val(e.get("storageUri"))
        if prop is None or d_from is None or d_to is None or not uri:
            continue
        w = _overlap(d_from, d_to, lo, hi)
        if w <= 0:
            continue
        mean = await asyncio.to_thread(_read_zonal_mean, s3, uri, geometry)
        if mean is not None:
            acc.setdefault(prop, []).append((mean, w))
    out = {p: sum(v * w for v, w in vs) / sum(w for _, w in vs) for p, vs in acc.items()}
    return out or None


async def _lucas_in_zone(geometry: dict) -> dict[str, float] | None:
    return await LucasProvider().values_in_polygon(geometry)


# --------------------------------------------------------------- composition

def _complete_texture(vals: dict) -> dict | None:
    """sand/silt/clay all present (silt derived from the other two if missing)."""
    sand, silt, clay = vals.get("sand"), vals.get("silt"), vals.get("clay")
    if sand is None or clay is None:
        return None
    if silt is None:
        silt = round(100.0 - sand - clay, 3)
        if silt < 0:
            return None
    return {**vals, "silt": silt}


def _parcel_horizon(parcel_summary: dict, depth: tuple[int, int]) -> dict:
    """Thickness-weighted mean of the parcel horizons overlapping the depth range;
    categorical fields come from the horizon with the largest overlap."""
    lo, hi = depth
    rows = []
    for h in parcel_summary.get("horizons", []):
        d_from, d_to = _num(h.get("depthFrom")), _num(h.get("depthTo"))
        if d_from is None or d_to is None:
            continue
        w = _overlap(d_from, d_to, lo, hi)
        if w > 0:
            rows.append((w, h))
    out: dict = {}
    for k in _NUMERIC_KEYS:
        pairs = [(w, _num(h.get(k))) for w, h in rows if _num(h.get(k)) is not None]
        out[k] = round(sum(w * v for w, v in pairs) / sum(w for w, _ in pairs), 4) if pairs else None
    for k in _CATEGORICAL_KEYS:
        cands = [(w, h.get(k)) for w, h in rows if h.get(k) is not None]
        out[k] = max(cands, key=lambda c: c[0])[1] if cands else None
    return out


def _with_pedotransfer(vals: dict, parcel_h: dict, depth: tuple[int, int]) -> dict:
    """Texture from the zone source; organic carbon and pH from that source when it
    has them, else the parcel's. FC/WP/AWC/Ksat/group/class re-derived consistently."""
    from nkz_soil.workers.ingest import EnrichedHorizon, _apply_pedotransfer, _horizon_to_dict

    h = EnrichedHorizon(
        depth_from=depth[0], depth_to=depth[1],
        sand=vals["sand"], silt=vals["silt"], clay=vals["clay"],
        organic_carbon=vals.get("organic_carbon", parcel_h.get("organicCarbon")),
        ph=vals.get("ph", parcel_h.get("ph")),
    )
    _apply_pedotransfer([h])
    d = _horizon_to_dict(h)
    return {k: d.get(k) for k in _HORIZON_KEYS}


def _result(zone: dict, provider: str, fidelity: str, horizon: dict) -> dict:
    return {
        "zoneId": zone["zoneId"], "zoneVersion": zone["zoneVersion"],
        "fidelity": fidelity, "provider": provider, "horizon": horizon,
    }


def _lab_values(points: list[dict], depth: tuple[int, int]) -> dict | None:
    lo, hi = depth
    acc: dict[str, list[float]] = {}
    for p in points:
        for h in horizons_of(p):
            d_from, d_to = _num(h.get("depthFrom")), _num(h.get("depthTo"))
            if d_from is None or d_to is None or _overlap(d_from, d_to, lo, hi) <= 0:
                continue
            for key, field in _SOURCE_FIELDS:
                v = _num(h.get(key))
                if v is not None:
                    acc.setdefault(field, []).append(v)
    return {f: round(sum(v) / len(v), 4) for f, v in acc.items()} or None


def _class_areas(features: list[dict], clip) -> dict[str, float]:
    areas: dict[str, float] = {}
    for f in features:
        label = IdenaProvider.class_of_feature(f)
        if label is None or not f.get("geometry"):
            continue
        area = shape(f["geometry"]).intersection(clip).area
        if area > 0:
            areas[label] = areas.get(label, 0.0) + area
    return areas


async def _idena_zone_values(parcel_summary: dict, geometry: dict, ctx: dict) -> dict | None:
    zone = shape(geometry)
    provider = IdenaProvider()
    zone_areas = _class_areas(await provider.features_for_bbox(*zone.bounds), zone)
    if not zone_areas:
        return None
    zone_dom = max(zone_areas, key=zone_areas.get)

    if "idena_parcel" not in ctx:
        pgeom = parcel_summary.get("parcelGeometry")
        if pgeom:
            parcel = shape(pgeom)
            ctx["idena_parcel"] = _class_areas(await provider.features_for_bbox(*parcel.bounds), parcel)
        else:
            ctx["idena_parcel"] = {}
    parcel_areas = ctx["idena_parcel"]
    if not parcel_areas:
        return None  # parcel footprint unknown: cannot show the zone differs
    parcel_dom = max(parcel_areas, key=parcel_areas.get)
    if len(parcel_areas) < 2 and zone_dom == parcel_dom:
        return None
    sand, silt, clay = TEXTURE_CLASS_FRACTIONS[zone_dom]
    return {"sand": sand, "silt": silt, "clay": clay}


async def resolve_zone_soil(
    tenant: str,
    parcel_id: str,
    parcel_summary: dict,
    zone: dict,
    depth: str = "0-60",
    ctx: dict | None = None,
) -> dict:
    ctx = ctx if ctx is not None else {}
    rng = _parse_depth(depth)
    geometry = zone["geometry"]
    parcel_h = _parcel_horizon(parcel_summary, rng)
    degraded = False

    async def attempt(name: str, coro):
        nonlocal degraded
        try:
            return await coro
        except Exception:
            degraded = True
            logger.warning(
                "zonal source failed", extra={"source": name, "tenant": tenant, "parcel": parcel_id,
                                              "zone": zone["zoneId"]}, exc_info=True,
            )
            return None

    def specific(provider: str, vals: dict | None) -> dict | None:
        tex = _complete_texture(vals) if vals else None
        if tex is None:
            return None
        return _result(zone, provider, ZONE_SPECIFIC, _with_pedotransfer(tex, parcel_h, rng))

    points = await attempt("lab_analysis", _sampling_points_in_zone(tenant, geometry))
    res = specific("lab_analysis", _lab_values(points, rng)) if points else None
    if res is None:
        res = specific("derived_raster", await attempt(
            "derived_raster", _raster_values_in_zone(tenant, parcel_id, geometry, rng)))
    if res is None:
        res = specific("idena", await attempt("idena", _idena_zone_values(parcel_summary, geometry, ctx)))
    if res is None:
        res = specific("LUCAS", await attempt("lucas", _lucas_in_zone(geometry)))
    if res is None:
        source = _val(parcel_summary.get("dataSource")) or "unknown"
        res = _result(zone, source, PARCEL_INHERITED, {k: parcel_h.get(k) for k in _HORIZON_KEYS})
    if degraded:
        res["_degraded"] = True
    return res


async def resolve_zone_soil_cached(
    tenant: str, parcel_id: str, parcel_summary: dict, zone: dict,
    depth: str = "0-60", ctx: dict | None = None,
) -> dict:
    key = _cache_key(tenant, parcel_id, zone, depth)
    try:
        hit = await _cache_client().get(key)
        if hit:
            return json.loads(hit)
    except Exception:
        logger.warning("zonal cache read failed", extra={"key": key}, exc_info=True)
    res = await resolve_zone_soil(tenant, parcel_id, parcel_summary, zone, depth, ctx)
    if res.pop("_degraded", False):
        return res
    try:
        await _cache_client().set(key, json.dumps(res), ex=CACHE_TTL_SECONDS)
    except Exception:
        logger.warning("zonal cache write failed", extra={"key": key}, exc_info=True)
    return res
