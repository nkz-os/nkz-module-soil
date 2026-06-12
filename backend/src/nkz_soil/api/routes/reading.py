from fastapi import APIRouter, HTTPException, Query

from nkz_platform_sdk import AuthContext
from nkz_soil.api.dependencies import require_auth
from nkz_soil.api.limiter import limiter
from nkz_soil.api.routes import providers as provider_routes
from nkz_soil.models.domain import DepthInterval
from nkz_soil.pedotransfer.saxton_rawls import saxton_rawls_2006
from nkz_soil.pedotransfer.usda_texture import usda_texture_class
from nkz_soil.pedotransfer.scs_groups import scs_hydrologic_group
from nkz_soil.storage.orion import OrionClient, parcel_ref_query

router = APIRouter()


async def _first_agri_soil(orion: OrionClient, parcel_id: str) -> dict:
    entities = await orion.query_entities(
        type="AgriSoilExtended",
        q=parcel_ref_query(parcel_id),
        limit=1,
    )
    if not entities:
        raise HTTPException(status_code=404, detail="No AgriSoil found for this parcel")
    return entities[0]


@router.get("/parcel/{parcel_id}/summary")
@limiter.exempt
async def parcel_summary(parcel_id: str, auth: AuthContext = require_auth()):
    async with OrionClient(auth.tenant_id) as orion:
        return await _first_agri_soil(orion, parcel_id)


@router.get("/parcel/{parcel_id}/horizons")
@limiter.exempt
async def parcel_horizons(
    parcel_id: str, depth: str = "0-30", auth: AuthContext = require_auth()
):
    depth_from, depth_to = map(int, depth.split("-"))
    async with OrionClient(auth.tenant_id) as orion:
        entity = await _first_agri_soil(orion, parcel_id)
        horizons = entity.get("horizons", {}).get("value", [])
        filtered = [
            h
            for h in horizons
            if h["depthFrom"] >= depth_from and h["depthTo"] <= depth_to
        ]
        return {"horizons": filtered}


@router.get("/parcel/{parcel_id}/raster")
@limiter.exempt
async def parcel_raster(
    parcel_id: str,
    property: str,
    depth: str = "0-30",
    auth: AuthContext = require_auth(),
):
    async with OrionClient(auth.tenant_id) as orion:
        depth_from, depth_to = map(int, depth.split("-"))
        entities = await orion.query_entities(
            type="SoilDerivedRaster",
            q=parcel_ref_query(parcel_id),
        )
        matching = [
            e
            for e in entities
            if (
                e.get("property", {}).get("value") == property
                and e.get("depthFrom", {}).get("value") == depth_from
                and e.get("depthTo", {}).get("value") == depth_to
            )
        ]
        if not matching:
            raise HTTPException(status_code=404, detail="No raster found")
        from nkz_soil.storage.minio import generate_presigned_url, get_minio_client

        s3 = get_minio_client()
        raster = matching[0]
        uri = raster.get("storageUri", {}).get("value", "")
        bucket, key = uri.replace("s3://", "").split("/", 1)
        url = generate_presigned_url(s3, bucket, key)
        return {"url": url, "metadata": raster}


@router.get("/parcel/{parcel_id}/hydrologic-group")
@limiter.exempt
async def parcel_hydrologic_group(
    parcel_id: str, auth: AuthContext = require_auth()
):
    async with OrionClient(auth.tenant_id) as orion:
        entity = await _first_agri_soil(orion, parcel_id)
        horizons = entity.get("horizons", {}).get("value", [])
        if not horizons:
            raise HTTPException(status_code=404, detail="No horizons found")
        group = horizons[0].get("hydrologicGroup", "B")
        return {"parcelId": parcel_id, "hydrologicGroup": group}


@router.get("/point")
@limiter.exempt
async def point_query(
    lat: float, lon: float, depth: str = "0-30", auth: AuthContext = require_auth()
):
    depth_from, depth_to = map(int, depth.split("-"))
    geometry = {"type": "Point", "coordinates": [lon, lat]}
    async with OrionClient(auth.tenant_id) as orion:
        entities = await orion.query_entities(type="AgriSoilExtended", geometry=geometry)
        if not entities:
            raise HTTPException(status_code=404, detail="No soil data at this point")
        horizons = entities[0].get("horizons", {}).get("value", [])
        filtered = [
            h
            for h in horizons
            if h["depthFrom"] >= depth_from and h["depthTo"] <= depth_to
        ]
        return {
            "horizons": filtered,
            "source": entities[0].get("dataSource", {}).get("value"),
        }


@router.get("/penetrometer/{parcel_id}")
@limiter.exempt
async def penetrometer_readings(
    parcel_id: str,
    auth: AuthContext = require_auth(),
):
    """Return SoilSamplingPoint entities with penetrationResistance for a parcel."""
    async with OrionClient(auth.tenant_id) as orion:
        entities = await orion.query_entities(
            type="SoilSamplingPoint",
            q=parcel_ref_query(parcel_id),
        )

    points = []
    for e in entities:
        horizons = e.get("horizons", {}).get("value", [])
        if not horizons:
            continue
        # Penetrometer readings use a single depth interval per sampling point.
        # Use the first horizon; higher-depth readings require a separate point.
        h = horizons[0]
        pr = h.get("penetrationResistance")
        if pr is None or not isinstance(pr, (int, float)):
            continue

        loc = e.get("location", {}).get("value", {})
        coords = loc.get("coordinates", [])
        if len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]

        sd = e.get("samplingDate", {}).get("value")
        date_str = sd[:10] if sd and isinstance(sd, str) else None

        points.append({
            "id": e.get("id"),
            "lat": lat,
            "lon": lon,
            "depthFrom": h.get("depthFrom"),
            "depthTo": h.get("depthTo"),
            "resistance": pr,
            "date": date_str,
        })

    return {"points": points}


@router.get("/tenant/quota")
@limiter.exempt
async def tenant_quota(auth: AuthContext = require_auth()):
    """Calculate evaluated hectares from AgriSoil entities in Orion-LD."""
    from shapely.geometry import shape
    from shapely.ops import transform
    import pyproj

    async with OrionClient(auth.tenant_id) as orion:
        entities = await orion.query_entities(type="AgriSoilExtended")

    total_area_m2 = 0.0
    for entity in entities:
        geometry = entity.get("location", {}).get("value")
        if not geometry:
            continue
        try:
            geom = shape(geometry)
            # Transform to area-preserving projection for accurate calculation
            geom_proj = transform(
                pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform,
                geom,
            )
            total_area_m2 += geom_proj.area
        except Exception:
            continue

    evaluated_ha = round(total_area_m2 / 10_000, 2)

    return {
        "tenantId": auth.tenant_id,
        "evaluatedHectares": evaluated_ha,
        "contractedHectares": 0,  # TODO: configurable per tenant
        "soilEntities": len(entities),
    }


# ---------------------------------------------------------------------------
# On-the-fly texture resolution — canonical endpoint for other platform
# services (weather-api, risk-worker, crop-health) to obtain soil texture
# at any point without requiring a pre-existing AgriSoilExtended entity.
# ---------------------------------------------------------------------------

_DEFAULT_DEPTH = "0-5"

# LUCAS-supported depth intervals (the only ones the KNN provider returns)
_LUCAS_DEPTHS = [(0, 5), (5, 15), (15, 30)]


def _split_depth(depth_from: int, depth_to: int) -> list[tuple[int, int]]:
    """Split a requested depth range into LUCAS-compatible sub-intervals."""
    intervals = []
    for ld_from, ld_to in _LUCAS_DEPTHS:
        if ld_to <= depth_from:
            continue
        if ld_from >= depth_to:
            break
        intervals.append((max(ld_from, depth_from), min(ld_to, depth_to)))
    return intervals or [(depth_from, depth_to)]


@router.get("/point/texture")
@limiter.exempt
async def point_texture(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    depth: str = Query(_DEFAULT_DEPTH, pattern=r"^\d+-\d+$"),
    auth: AuthContext = require_auth(),
):
    """Resolve soil texture on-the-fly for any geographic point.

    Triggers the full provider chain (LUCAS → SoilGrids → ESDB → …) but does
    NOT persist the result to Orion-LD.  This is a read-only query — use
    POST /parcel/{id}/ingest when you need the result stored as AgriSoilExtended.

    Returns sand, clay, silt, organicCarbon (all %), plus Saxton-Rawls (2006)
    derived properties: fieldCapacity, wiltingPoint, saturatedHydraulicConductivity,
    hydrologicGroup (SCS), and usdaTextureClass.

    This is the canonical endpoint for any platform service that needs soil
    texture data at a specific point (e.g. weather-api agro-status, risk-worker
    workability models, crop-health water balance).
    """
    depth_from, depth_to = map(int, depth.split("-"))
    geometry = {"type": "Point", "coordinates": [lon, lat]}
    sub_intervals = _split_depth(depth_from, depth_to)
    depth_intervals = [
        DepthInterval(depth_from=df, depth_to=dt) for df, dt in sub_intervals
    ]

    if not provider_routes._registry:
        raise HTTPException(
            status_code=503,
            detail="Soil provider registry not initialized",
        )

    # Try each provider in priority order until one returns actual texture data.
    # A provider may return non-empty horizons with sand/clay/silt all None
    # (e.g. LUCAS 2018 topsoil which lacks texture columns). Keep trying
    # lower-priority providers until we get real sand/clay/silt values.
    providers = provider_routes._registry.get_all()
    result = None
    for provider in providers:
        if not provider.covers(geometry):
            continue
        try:
            result = await provider.fetch(geometry, [], depth_intervals)
            if result and result.horizons:
                # Only accept if the provider returned actual texture values
                h = result.horizons[0]
                if h.sand is not None or h.clay is not None or h.silt is not None:
                    break
        except Exception:
            continue

    if not result or not result.horizons:
        raise HTTPException(
            status_code=404,
            detail="No soil data available at this location from any provider",
        )

    # Use top horizon for texture properties (most relevant for agriculture)
    h = result.horizons[0]
    sand = h.sand or 0.0
    clay = h.clay or 0.0
    silt = h.silt or max(0.0, 100.0 - sand - clay)
    oc = h.organic_carbon or 0.5

    # USDA texture class
    tc = usda_texture_class(sand, silt, clay)

    # Saxton-Rawls 2006 pedotransfer
    ptf = saxton_rawls_2006(sand, clay, oc)

    # SCS hydrologic group
    hg = scs_hydrologic_group(ptf["ksat"])

    return {
        "point": {"lat": lat, "lon": lon},
        "depth": {"from": depth_from, "to": depth_to},
        "texture": {
            "sand": sand,
            "clay": clay,
            "silt": silt,
            "organicCarbon": oc,
            "usdaTextureClass": tc,
        },
        "hydraulic": {
            "fieldCapacity": ptf["field_capacity"],
            "wiltingPoint": ptf["wilting_point"],
            "saturatedHydraulicConductivity": ptf["ksat"],
            "hydrologicGroup": hg,
        },
        "source": {
            "provider": result.provider,
            "attribution": result.attribution,
            "license": result.license,
            "uncertainty": result.uncertainty,
        },
    }


@router.get("/parcel/{parcel_id}/compaction-susceptibility")
@limiter.exempt
async def parcel_compaction_susceptibility(
    parcel_id: str, auth: AuthContext = require_auth()
):
    """Return compaction susceptibility for a parcel from its AgriSoil entity.

    Returns per-horizon susceptibility scores + overall aggregation.
    Cross-module endpoint for crop-health and other consumers.
    """
    async with OrionClient(auth.tenant_id) as orion:
        entity = await _first_agri_soil(orion, parcel_id)
        horizons = entity.get("horizons", {}).get("value", [])

        # Extract per-horizon susceptibility
        by_horizon = []
        for h in horizons:
            cs = h.get("compactionSusceptibility")
            if cs:
                by_horizon.append({
                    "depthFrom": h.get("depthFrom"),
                    "depthTo": h.get("depthTo"),
                    "score": cs.get("score"),
                    "class": cs.get("class"),
                    "texturalScore": cs.get("texturalScore"),
                    "modifiersApplied": cs.get("modifiersApplied", []),
                    "indicativeElevatedBd": cs.get("indicativeElevatedBd", False),
                })

        # Top-level aggregation from entity property
        overall = entity.get("compactionSusceptibility", {}).get("value", {})

        return {
            "parcelId": parcel_id,
            "overall": {
                "score": overall.get("overallScore"),
                "class": overall.get("overallClass"),
                "worstHorizonScore": overall.get("worstHorizonScore"),
                "worstHorizonClass": overall.get("worstHorizonClass"),
            },
            "byHorizon": by_horizon,
        }
