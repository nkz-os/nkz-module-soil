import csv
import io
import uuid

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel

from nkz_platform_sdk import AuthContext
from nkz_soil.api.dependencies import get_redis_pool, require_auth
from nkz_soil.config import BATCH_MAX_BYTES, BATCH_MAX_ROWS, CONTEXT_URL
from nkz_soil.storage.orion import OrionClient, parcel_ref_query

router = APIRouter()


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
    laboratory_reference: str | None = None
    sampling_date: str | None = None
    operator: str | None = None


class SurveyInput(BaseModel):
    survey_type: str
    parcel_id: str | None = None
    instrumentation: str | None = None


@router.post("/sampling-points")
async def create_sampling_point(
    body: SamplingPointInput, auth: AuthContext = require_auth()
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

    entity_id = f"urn:ngsi-ld:SoilSamplingPoint:{uuid.uuid4()}"
    entity = {
        "id": entity_id,
        "type": "SoilSamplingPoint",
        "@context": [CONTEXT_URL],
        "location": {
            "type": "GeoProperty",
            "value": {"type": "Point", "coordinates": [body.lon, body.lat]},
        },
        "samplingDate": {"type": "Property", "value": body.sampling_date},
        "laboratoryReference": {
            "type": "Property",
            "value": body.laboratory_reference,
        },
        "horizons": {
            "type": "Property",
            "value": [
                {
                    "depthFrom": body.depth_from,
                    "depthTo": body.depth_to,
                    "sand": body.sand,
                    "silt": body.silt,
                    "clay": body.clay,
                    "organicCarbon": body.organic_carbon,
                    "bulkDensity": body.bulk_density,
                    "ph": body.ph,
                    "cec": body.cec,
                    "coarseFragments": body.coarse_fragments,
                    "penetrationResistance": body.penetration_resistance,
                }
            ],
        },
        "operator": {"type": "Property", "value": body.operator},
    }

    async with OrionClient(tenant_id) as orion:
        await orion.create_entity(entity)

    return {"id": entity_id, "status": "created"}


@router.post("/surveys")
async def create_survey(body: SurveyInput, auth: AuthContext = require_auth()):
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
            "object": f"urn:ngsi-ld:AgriParcel:{body.parcel_id}",
        }

    async with OrionClient(tenant_id) as orion:
        await orion.create_entity(entity)

    return {"id": entity_id, "status": "created"}


@router.post("/parcel/{parcel_id}/ingest")
async def force_ingest(
    parcel_id: str,
    request: Request,
    auth: AuthContext = require_auth(),
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
]

# Aliases for common variations
_CSV_ALIASES = {
    "depth_from": "depthFrom", "depth_to": "depthTo",
    "organic_carbon": "organicCarbon", "bulk_density": "bulkDensity",
    "coarse_fragments": "coarseFragments", "penetration_resistance": "penetrationResistance",
    "lab_reference": "labReference", "sampling_date": "samplingDate",
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
    cleaned["sampling_date"] = row.get("samplingDate", "") or None
    cleaned["operator"] = row.get("operator", "") or None

    return cleaned, None


def _sampling_point_entity(cleaned: dict) -> tuple[str, dict]:
    entity_id = f"urn:ngsi-ld:SoilSamplingPoint:{uuid.uuid4()}"
    entity = {
        "id": entity_id,
        "type": "SoilSamplingPoint",
        "@context": [CONTEXT_URL],
        "location": {
            "type": "GeoProperty",
            "value": {"type": "Point", "coordinates": [cleaned["lon"], cleaned["lat"]]},
        },
        "samplingDate": {"type": "Property", "value": cleaned["sampling_date"]},
        "laboratoryReference": {
            "type": "Property",
            "value": cleaned["laboratory_reference"],
        },
        "horizons": {
            "type": "Property",
            "value": [
                {
                    "depthFrom": cleaned["depth_from"],
                    "depthTo": cleaned["depth_to"],
                    "sand": cleaned.get("sand"),
                    "silt": cleaned.get("silt"),
                    "clay": cleaned.get("clay"),
                    "organicCarbon": cleaned.get("organic_carbon"),
                    "bulkDensity": cleaned.get("bulk_density"),
                    "ph": cleaned.get("ph"),
                    "cec": cleaned.get("cec"),
                    "coarseFragments": cleaned.get("coarse_fragments"),
                    "penetrationResistance": cleaned.get("penetration_resistance"),
                }
            ],
        },
        "operator": {"type": "Property", "value": cleaned["operator"]},
    }
    return entity_id, entity


@router.post("/sampling-points/batch")
async def create_sampling_points_batch(
    file: UploadFile = File(...),
    auth: AuthContext = require_auth(),
):
    tenant_id = auth.tenant_id
    """Upload CSV file with multiple soil sampling points.

    CSV columns: lat, lon, depthFrom, depthTo, sand, silt, clay,
    organicCarbon, ph, cec, bulkDensity, coarseFragments,
    penetrationResistance, labReference, samplingDate, operator.
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
        entity_id, entity = _sampling_point_entity(cleaned)
        row_by_entity_id[entity_id] = row_num
        entities.append(entity)

    async with OrionClient(tenant_id) as orion:
        batch_result = await orion.create_entities_batch(entities)

    created = [
        {"id": eid, "row": row_by_entity_id[eid]}
        for eid in batch_result.get("entity_ids", [])
        if eid in row_by_entity_id
    ]
    for err in batch_result.get("errors", []):
        if isinstance(err, dict):
            eid = err.get("id", "")
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
    auth: AuthContext = require_auth(),
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
            type="SoilSamplingPoint",
            q=parcel_ref_query(parcel_id),
        )

        sample_points = []
        for e in matching:
            loc = e.get("location", {}).get("value", {})
            coords = loc.get("coordinates", [])
            if len(coords) < 2:
                # Try GeoProperty alternate format
                if loc.get("type") == "Point":
                    coords = loc.get("coordinates", [])
            if len(coords) < 2:
                continue

            prop_val = e.get(property)
            if isinstance(prop_val, dict):
                prop_val = prop_val.get("value")
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
