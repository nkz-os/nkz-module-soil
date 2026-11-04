import csv
import io
import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

import httpx
from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from nkz_platform_sdk import AuthContext
from pydantic import BaseModel

from nkz_soil.api.dependencies import get_redis_pool, require_auth
from nkz_soil.config import BATCH_MAX_BYTES, BATCH_MAX_ROWS, CONTEXT_URL
from nkz_soil.models.agri_soil_sample import SOIL_SAMPLE_TYPES, to_entity
from nkz_soil.models.fertility import (
    FERTILITY_FIELDS,
    has_fertility_values,
    validate_fertility,
    validate_sampling_date,
)
from nkz_soil.pedotransfer.usda_texture import USDA_TEXTURE_CLASSES
from nkz_soil.services.zonal import invalidate_parcel
from nkz_soil.storage.orion import OrionClient, parcel_ref_query
from nkz_soil.util.declared_texture import ATTR as DECLARED_TEXTURE_ATTR
from nkz_soil.util.ngsi import horizons_of


def _num(v):
    return v.get("value") if isinstance(v, dict) else v


def _overlaps(df, dt, depth_from: int, depth_to: int) -> bool:
    return (
        isinstance(df, (int, float)) and isinstance(dt, (int, float))
        and dt > depth_from and df < depth_to
    )


def _sampling_value(entity: dict, property: str, depth_from: int, depth_to: int):
    """Property value of a SoilSamplingPoint for the requested depth range.

    Sampling properties live in ``horizons``; only the horizon overlapping the
    requested range counts (a point sampled at 0-30 says nothing about 30-60).
    The root attribute is a legacy fallback used only when the entity has no
    horizons and its own root depth range overlaps; a root value without depth
    is discarded (unknown beats a wrong figure).
    """
    horizons = horizons_of(entity)
    if horizons:
        for h in horizons:
            if _overlaps(h.get("depthFrom"), h.get("depthTo"), depth_from, depth_to):
                v = _num(h.get(property))
                if v is not None:
                    return v
        return None
    if _overlaps(
        _num(entity.get("depthFrom")), _num(entity.get("depthTo")), depth_from, depth_to
    ):
        return _num(entity.get(property))
    return None


logger = logging.getLogger(__name__)
router = APIRouter()
_REQUIRE_AUTH = require_auth()
_FILE_UPLOAD = File(...)


_PARCEL_URN_PREFIX = "urn:ngsi-ld:AgriParcel:"


def _parcel_urn(parcel_id: str) -> str:
    """Return canonical parcel URN, normalizing short id or full URN."""
    if parcel_id.startswith(_PARCEL_URN_PREFIX):
        return parcel_id
    return f"{_PARCEL_URN_PREFIX}{parcel_id}"


class SamplingPointInput(BaseModel):
    lat: float
    lon: float
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
    penetration_resistance: float | None = None
    organic_matter: float | None = None
    total_nitrogen: float | None = None
    nitrate_n: float | None = None
    ammonium_n: float | None = None
    phosphorus_available: float | None = None
    phosphorus_method: str | None = None
    potassium_exchangeable: float | None = None
    potassium_method: str | None = None
    carbonates: float | None = None
    active_lime: float | None = None
    parcel_id: str | None = None
    laboratory_reference: str | None = None
    sampling_date: str | None = None
    operator: str | None = None
    zone_id: str | None = None
    number_of_subsamples: int | None = None


_ZONE_URN_PREFIX = "urn:ngsi-ld:AgriManagementZone:"


def _validate_sample_extras(values: dict) -> list[str]:
    """Optional zone link and number of pooled subsamples of a soil sample."""
    errors = []
    zone = values.get("zone_id")
    if zone is not None and (not isinstance(zone, str) or not zone.startswith(_ZONE_URN_PREFIX)):
        errors.append(f"zoneId must be a {_ZONE_URN_PREFIX}... URN")
    n = values.get("number_of_subsamples")
    if n is not None and (isinstance(n, bool) or not isinstance(n, int) or n < 1):
        errors.append("numberOfSubsamples must be a whole number >= 1")
    return errors


class SurveyInput(BaseModel):
    survey_type: str
    parcel_id: str | None = None
    instrumentation: str | None = None


@router.post("/sampling-points")
async def create_sampling_point(
    body: SamplingPointInput, auth: AuthContext = _REQUIRE_AUTH
):
    tenant_id = auth.tenant_id
    if body.sand is not None and body.silt is not None and body.clay is not None:
        total = body.sand + body.silt + body.clay
        if total < 97 or total > 103:
            raise HTTPException(
                status_code=422,
                detail=f"sand+silt+clay must be ~100%, got {total}",
            )
    if body.ph is not None and (body.ph < 0 or body.ph > 14):
        raise HTTPException(status_code=422, detail="pH must be 0-14")
    if body.bulk_density is not None and (
        body.bulk_density < 0.1 or body.bulk_density > 2.65
    ):
        raise HTTPException(
            status_code=422, detail="bulkDensity must be 0.1-2.65 g/cm3"
        )

    values = body.model_dump()
    errors = validate_fertility(values) + validate_sampling_date(
        values.get("sampling_date"), required=has_fertility_values(values),
    ) + _validate_sample_extras(values)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    # Interactive entry: a fresh id per reading (several penetrometer readings at one spot
    # are all kept). Only CSV imports use the deterministic id, to make re-imports updates.
    entity_id = f"urn:ngsi-ld:AgriSoilSample:{tenant_id}:{uuid.uuid4().hex[:16]}"
    entity = to_entity(tenant_id, values, entity_id=entity_id)
    async with OrionClient(tenant_id) as orion:
        result = await orion.upsert_entities_batch([entity])
    if result.get("errors"):
        logger.error("soil sample not stored: tenant=%s id=%s errors=%s",
                     tenant_id, entity_id, result["errors"])
        raise HTTPException(status_code=502, detail="Soil sample could not be stored")

    # A new point can change the per-zone soil of its parcel (or, unlinked, any).
    await invalidate_parcel(tenant_id, body.parcel_id)

    return {"id": entity_id, "status": "created"}


class DeclaredTextureInput(BaseModel):
    usda_texture_class: Literal[USDA_TEXTURE_CLASSES]  # type: ignore[valid-type]


async def _soil_entity_id(orion: OrionClient, parcel_id: str) -> str:
    entities = await orion.query_entities(
        type="AgriSoilExtended", q=parcel_ref_query(parcel_id), limit=1
    )
    if not entities:
        raise HTTPException(status_code=404, detail="No AgriSoil found for this parcel")
    return entities[0]["id"]


@router.put("/parcel/{parcel_id}/declared-texture")
async def put_declared_texture(
    parcel_id: str, body: DeclaredTextureInput, auth: AuthContext = _REQUIRE_AUTH
):
    """Declare the USDA texture class of the parcel topsoil (provenance 'entered').

    Never a SoilSamplingPoint: it is not an analysis. Readers prefer a measured
    value over it, and a re-ingest leaves it untouched.
    """
    async with OrionClient(auth.tenant_id) as orion:
        entity_id = await _soil_entity_id(orion, parcel_id)
        await orion.append_entity_attrs(entity_id, {
            DECLARED_TEXTURE_ATTR: {
                "type": "Property",
                "value": body.usda_texture_class,
                "observedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        })
    return {
        "parcelId": parcel_id,
        "usdaTextureClass": body.usda_texture_class,
        "source": "entered",
    }


@router.delete("/parcel/{parcel_id}/declared-texture", status_code=204)
async def delete_declared_texture(parcel_id: str, auth: AuthContext = _REQUIRE_AUTH):
    """Withdraw a declaration; readers fall back to the estimated value. Idempotent."""
    async with OrionClient(auth.tenant_id) as orion:
        entity_id = await _soil_entity_id(orion, parcel_id)
        try:
            await orion.delete_entity_attr(entity_id, DECLARED_TEXTURE_ATTR)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
    return Response(status_code=204)


@router.post("/surveys")
async def create_survey(body: SurveyInput, auth: AuthContext = _REQUIRE_AUTH):
    tenant_id = auth.tenant_id
    if body.survey_type not in ("lab", "em", "nir", "auger"):
        raise HTTPException(
            status_code=422,
            detail="surveyType must be lab, em, nir, or auger",
        )

    entity_id = f"urn:ngsi-ld:SoilSurvey:{uuid.uuid4()}"
    entity: dict = {
        "id": entity_id,
        "type": "SoilSurvey",
        "@context": [CONTEXT_URL],
        "surveyType": {"type": "Property", "value": body.survey_type},
        "startDate": {"type": "Property", "value": None},
        "instrumentation": {"type": "Property", "value": body.instrumentation},
        "pointCount": {"type": "Property", "value": 0},
        "tenant": {"type": "Property", "value": tenant_id},
    }
    if body.parcel_id:
        entity["hasAgriParcel"] = {
            "type": "Relationship",
            "object": _parcel_urn(body.parcel_id),
        }

    async with OrionClient(tenant_id) as orion:
        await orion.create_entity(entity)

    return {"id": entity_id, "status": "created"}


@router.post("/parcel/{parcel_id}/ingest")
async def force_ingest(
    parcel_id: str,
    request: Request,
    auth: AuthContext = _REQUIRE_AUTH,
):
    redis = get_redis_pool(request)
    await redis.enqueue_job("ingest_parcel", parcel_id, auth.tenant_id, {}, "v1")

    return {"status": "accepted", "parcelId": parcel_id}


# CSV column mapping: accepts both snake_case and camelCase
_CSV_COLUMNS = [
    "lat", "lon", "depthFrom", "depthTo",
    "sand", "silt", "clay", "organicCarbon", "ph",
    "cec", "bulkDensity", "coarseFragments", "penetrationResistance",
    "labReference", "samplingDate", "operator",
    *(key for key, _lo, _hi in FERTILITY_FIELDS.values()),
    "phosphorusMethod", "potassiumMethod", "parcelId", "zoneId", "numberOfSubsamples",
]

# Aliases for common variations
_CSV_ALIASES = {
    "depth_from": "depthFrom", "depth_to": "depthTo",
    "organic_carbon": "organicCarbon", "bulk_density": "bulkDensity",
    "coarse_fragments": "coarseFragments", "penetration_resistance": "penetrationResistance",
    "lab_reference": "labReference", "sampling_date": "samplingDate",
    "organic_matter": "organicMatter", "total_nitrogen": "totalNitrogen",
    "nitrate_n": "nitrateN", "ammonium_n": "ammoniumN",
    "phosphorus_available": "phosphorusAvailable", "phosphorus_method": "phosphorusMethod",
    "potassium_exchangeable": "potassiumExchangeable", "potassium_method": "potassiumMethod",
    "active_lime": "activeLime", "parcel_id": "parcelId",
    "zone_id": "zoneId", "number_of_subsamples": "numberOfSubsamples",
}


def _normalize_csv_headers(headers: list[str]) -> dict[str, str]:
    """Map CSV headers to canonical field names."""
    mapping = {}
    for h in headers:
        canonical = _CSV_ALIASES.get(h.strip(), h.strip())
        if canonical in _CSV_COLUMNS:
            mapping[h.strip()] = canonical
    return mapping


def _validate_row(row: dict, row_num: int) -> tuple[dict | None, str | None]:
    """Validate a single CSV row. Returns (cleaned_row, error)."""
    errors = []

    try:
        lat = float(row.get("lat", ""))
        lon = float(row.get("lon", ""))
    except (ValueError, TypeError):
        return None, f"Row {row_num}: invalid lat/lon"

    if not (-90 <= lat <= 90):
        errors.append("lat must be -90..90")
    if not (-180 <= lon <= 180):
        errors.append("lon must be -180..180")

    try:
        depth_from = int(row.get("depthFrom", ""))
        depth_to = int(row.get("depthTo", ""))
    except (ValueError, TypeError):
        return None, f"Row {row_num}: invalid depthFrom/depthTo"

    if depth_from < 0 or depth_to <= depth_from:
        errors.append("depthFrom must be >= 0 and < depthTo")

    # Texture validation
    sand = silt = clay = None
    for field, var in [("sand", "sand"), ("silt", "silt"), ("clay", "clay")]:
        val = row.get(field, "")
        if val:
            try:
                v = float(val)
                if field == "sand":
                    sand = v
                elif field == "silt":
                    silt = v
                else:
                    clay = v
            except ValueError:
                errors.append(f"invalid {field}")

    if sand is not None and silt is not None and clay is not None:
        total = sand + silt + clay
        if total < 97 or total > 103:
            errors.append(f"sand+silt+clay must be ~100%, got {total:.1f}")

    # pH validation
    ph_val = row.get("ph", "")
    if ph_val:
        try:
            ph = float(ph_val)
            if ph < 0 or ph > 14:
                errors.append("pH must be 0-14")
        except ValueError:
            errors.append("invalid ph")

    # Bulk density validation
    bd_val = row.get("bulkDensity", "")
    if bd_val:
        try:
            bd = float(bd_val)
            if bd < 0.1 or bd > 2.65:
                errors.append("bulkDensity must be 0.1-2.65")
        except ValueError:
            errors.append("invalid bulkDensity")

    fertility: dict = {}
    for name, (key, _lo, _hi) in FERTILITY_FIELDS.items():
        raw = row.get(key, "")
        if raw:
            try:
                fertility[name] = float(raw)
            except ValueError:
                errors.append(f"invalid {key}")
    if row.get("phosphorusMethod"):
        fertility["phosphorus_method"] = row["phosphorusMethod"].strip()
    if row.get("potassiumMethod"):
        fertility["potassium_method"] = row["potassiumMethod"].strip()
    errors.extend(validate_fertility(fertility))
    errors.extend(validate_sampling_date(
        row.get("samplingDate", "").strip() or None, required=has_fertility_values(fertility),
    ))
    extras: dict = {"zone_id": row.get("zoneId", "").strip() or None}
    raw_n = row.get("numberOfSubsamples", "").strip()
    if raw_n:
        try:
            extras["number_of_subsamples"] = int(raw_n)
        except ValueError:
            extras["number_of_subsamples"] = raw_n  # reported by _validate_sample_extras
    errors.extend(_validate_sample_extras(extras))

    if errors:
        return None, f"Row {row_num}: {'; '.join(errors)}"

    cleaned = {
        "lat": lat,
        "lon": lon,
        "depth_from": depth_from,
        "depth_to": depth_to,
    }
    for field, key in [
        ("sand", "sand"), ("silt", "silt"), ("clay", "clay"),
        ("organicCarbon", "organic_carbon"), ("ph", "ph"),
        ("cec", "cec"), ("bulkDensity", "bulk_density"),
        ("coarseFragments", "coarse_fragments"),
        ("penetrationResistance", "penetration_resistance"),
    ]:
        val = row.get(field, "")
        if val:
            try:
                cleaned[key] = float(val)
            except ValueError:
                pass

    cleaned["laboratory_reference"] = row.get("labReference", "") or None
    cleaned["sampling_date"] = row.get("samplingDate", "").strip() or None
    cleaned["operator"] = row.get("operator", "") or None
    cleaned.update(fertility)
    cleaned["parcel_id"] = row.get("parcelId", "").strip() or None
    cleaned.update(extras)

    return cleaned, None


@router.post("/sampling-points/batch")
async def create_sampling_points_batch(
    file: UploadFile = _FILE_UPLOAD,
    auth: AuthContext = _REQUIRE_AUTH,
):
    tenant_id = auth.tenant_id
    """Upload CSV file with multiple soil sampling points.

    CSV columns: lat, lon, depthFrom, depthTo, sand, silt, clay,
    organicCarbon, ph, cec, bulkDensity, coarseFragments,
    penetrationResistance, labReference, samplingDate, operator, organicMatter,
    totalNitrogen, nitrateN, ammoniumN, phosphorusAvailable, phosphorusMethod,
    potassiumExchangeable, potassiumMethod, carbonates, activeLime, parcelId.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="File must be a CSV")

    content = await file.read()
    if len(content) > BATCH_MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"CSV exceeds maximum size of {BATCH_MAX_BYTES} bytes",
        )
    text = content.decode("utf-8-sig")  # handle BOM

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=422, detail="Empty CSV or missing headers")

    header_map = _normalize_csv_headers(reader.fieldnames)
    if "lat" not in header_map.values() or "lon" not in header_map.values():
        raise HTTPException(
            status_code=422,
            detail="CSV must include 'lat' and 'lon' columns",
        )

    rows_to_create: list[tuple[int, dict]] = []
    errors: list[dict] = []

    for row_num, raw_row in enumerate(reader, start=2):
        if len(rows_to_create) >= BATCH_MAX_ROWS:
            errors.append({
                "row": row_num,
                "error": f"Exceeded maximum of {BATCH_MAX_ROWS} rows per upload",
            })
            break
        row = {header_map.get(k, k): v for k, v in raw_row.items() if v.strip()}
        cleaned, error = _validate_row(row, row_num)
        if error:
            errors.append({"row": row_num, "error": error})
            continue
        rows_to_create.append((row_num, cleaned))

    row_by_entity_id: dict[str, int] = {}
    entities: list[dict] = []
    for row_num, cleaned in rows_to_create:
        entity = to_entity(tenant_id, cleaned)
        first = row_by_entity_id.get(entity["id"])
        if first is not None:
            # Same parcel, point, day, depth and lab reference as an earlier row.
            errors.append({"row": row_num, "error": f"Row {row_num}: duplicate of row {first}"})
            continue
        row_by_entity_id[entity["id"]] = row_num
        entities.append(entity)

    # Deterministic ids + upsert: re-importing the same CSV updates, never duplicates.
    async with OrionClient(tenant_id) as orion:
        batch_result = await orion.upsert_entities_batch(entities)

    if entities:
        parcels = {c.get("parcel_id") for _, c in rows_to_create}
        for pid in parcels:
            await invalidate_parcel(tenant_id, pid)

    created = [
        {"id": eid, "row": row_by_entity_id[eid]}
        for eid in batch_result.get("entity_ids", [])
        if eid in row_by_entity_id
    ]
    for err in batch_result.get("errors", []):
        if isinstance(err, dict):
            eid = err.get("id") or err.get("entityId", "")
            if eid in row_by_entity_id:
                errors.append({
                    "row": row_by_entity_id[eid],
                    "error": err.get("error", str(err)),
                })
            else:
                errors.append({"row": 0, "error": str(err)})

    return {
        "created": len(created),
        "errors": len(errors),
        "details": created,
        "errorDetails": errors,
        "method": "batch",
    }


@router.post("/parcel/{parcel_id}/rasterize")
async def rasterize_parcel_property(
    parcel_id: str,
    property: str = "penetrationResistance",
    depth: str = "0-30",
    resolution: int = 5,
    auth: AuthContext = _REQUIRE_AUTH,
):
    """Generate an intra-parcel raster from SoilSamplingPoint measurements.

    Queries all SoilSamplingPoint entities linked to this parcel that have
    the requested property, interpolates via kriging/IDW, uploads a COG
    to MinIO, and registers a SoilDerivedRaster entity in Orion-LD.

    Requires at least 3 sampling points with the property.

    Returns the presigned MinIO URL for immediate map display.
    """
    from nkz_soil.interpolation.raster import generate_raster

    tenant_id = auth.tenant_id
    depth_from, depth_to = map(int, depth.split("-"))

    async with OrionClient(tenant_id) as orion:
        matching = await orion.query_entities(
            type=SOIL_SAMPLE_TYPES,
            q=parcel_ref_query(parcel_id),
        )

        sample_points = []
        for e in matching:
            loc = e.get("location", {}).get("value", {})
            coords = loc.get("coordinates", [])
            if len(coords) < 2 and loc.get("type") == "Point":
                # Try GeoProperty alternate format
                coords = loc.get("coordinates", [])
            if len(coords) < 2:
                continue

            prop_val = _sampling_value(e, property, depth_from, depth_to)
            if prop_val is None:
                continue

            sample_points.append({
                "x": float(coords[0]),
                "y": float(coords[1]),
                "value": float(prop_val),
            })

        if len(sample_points) < 3:
            raise HTTPException(
                status_code=400,
                detail=f"Need at least 3 sampling points with '{property}'. Found: {len(sample_points)}",
            )

        # Generate raster
        result = await generate_raster(
            tenant_id=tenant_id,
            parcel_id=parcel_id,
            property_name=property,
            depth_from=depth_from,
            depth_to=depth_to,
            sample_points=sample_points,
            resolution_m=resolution,
        )

        return {
            "parcelId": parcel_id,
            "property": property,
            "depth": depth,
            "resolution": resolution,
            "samplePoints": len(sample_points),
            "method": result["method"],
            "url": result["url"],
            "entityId": result["entity_id"],
        }
