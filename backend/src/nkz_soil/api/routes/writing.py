import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from nkz_soil.api.dependencies import get_tenant_id
from nkz_soil.config import CONTEXT_URL
from nkz_soil.storage.orion import OrionClient

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
    body: SamplingPointInput, tenant_id: str = Depends(get_tenant_id)
):
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
async def create_survey(body: SurveyInput, tenant_id: str = Depends(get_tenant_id)):
    if body.survey_type not in ("lab", "em", "nir", "auger"):
        raise HTTPException(
            status_code=422,
            detail="surveyType must be lab, em, nir, or auger",
        )

    entity_id = f"urn:ngsi-ld:SoilSurvey:{uuid.uuid4()}"
    entity = {
        "id": entity_id,
        "type": "SoilSurvey",
        "@context": [CONTEXT_URL],
        "surveyType": {"type": "Property", "value": body.survey_type},
        "refAgriParcel": (
            {
                "type": "Relationship",
                "object": f"urn:ngsi-ld:AgriParcel:{body.parcel_id}",
            }
            if body.parcel_id
            else None
        ),
        "startDate": {"type": "Property", "value": None},
        "instrumentation": {"type": "Property", "value": body.instrumentation},
        "pointCount": {"type": "Property", "value": 0},
        "tenant": {"type": "Property", "value": tenant_id},
    }

    async with OrionClient(tenant_id) as orion:
        await orion.create_entity(entity)

    return {"id": entity_id, "status": "created"}


@router.post("/parcel/{parcel_id}/ingest")
async def force_ingest(
    parcel_id: str, tenant_id: str = Depends(get_tenant_id)
):
    from arq.connections import ArqRedis
    from nkz_soil.config import REDIS_URL

    redis = ArqRedis.from_url(REDIS_URL)
    await redis.enqueue_job("ingest_parcel", parcel_id, tenant_id, {}, "v1")

    return {"status": "accepted", "parcelId": parcel_id}
