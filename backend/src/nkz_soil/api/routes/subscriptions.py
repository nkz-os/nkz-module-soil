import hashlib
import logging
from datetime import datetime, timezone

from arq.connections import ArqRedis
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from nkz_soil.api.limiter import limiter
from nkz_soil.config import CONTEXT_URL, REDIS_URL
from nkz_soil.storage.orion import OrionClient

logger = logging.getLogger(__name__)

router = APIRouter()

SUBSCRIPTION_ID = "urn:ngsi-ld:Subscription:soil-parcel-ingest"

INGESTION_BUFFER_M = 50.0


class OrionNotification(BaseModel):
    id: str
    type: str
    subscriptionId: str
    data: list[dict] | None = None


def _compute_parcel_hash(parcel_id: str, tenant_id: str, version: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{parcel_id}:{version}".encode()).hexdigest()[:16]


async def _is_already_processed(parcel_hash: str) -> bool:
    redis = ArqRedis.from_url(REDIS_URL)
    key = f"soil:ingested:{parcel_hash}"
    return await redis.exists(key) == 1


async def _mark_processed(parcel_hash: str, ttl: int = 86400) -> None:
    redis = ArqRedis.from_url(REDIS_URL)
    key = f"soil:ingested:{parcel_hash}"
    await redis.set(key, datetime.now(timezone.utc).isoformat(), ex=ttl)


def _expand_geometry(geometry: dict, buffer_m: float) -> dict:
    if geometry.get("type") == "Point":
        lon, lat = geometry["coordinates"]
        deg = buffer_m / 111320.0
        return {
            "type": "Polygon",
            "coordinates": [
                [
                    [lon - deg, lat - deg],
                    [lon + deg, lat - deg],
                    [lon + deg, lat + deg],
                    [lon - deg, lat + deg],
                    [lon - deg, lat - deg],
                ]
            ],
        }
    if geometry.get("type") == "Polygon":
        coords = geometry["coordinates"][0]
        centroid_lon = sum(c[0] for c in coords) / len(coords)
        centroid_lat = sum(c[1] for c in coords) / len(coords)
        deg = buffer_m / 111320.0
        min_lon = min(c[0] for c in coords) - deg
        max_lon = max(c[0] for c in coords) + deg
        min_lat = min(c[1] for c in coords) - deg
        max_lat = max(c[1] for c in coords) + deg
        return {
            "type": "Polygon",
            "coordinates": [
                [
                    [min_lon, min_lat],
                    [max_lon, min_lat],
                    [max_lon, max_lat],
                    [min_lon, max_lat],
                    [min_lon, min_lat],
                ]
            ],
        }
    return geometry


@router.post("/webhooks/orion")
@limiter.exempt
async def orion_webhook(request: Request):
    body = await request.json()

    notification_id = body.get("id", "")
    entity_type = body.get("type", "")
    subscription_id = body.get("subscriptionId", "")
    data = body.get("data", [])

    if subscription_id != SUBSCRIPTION_ID:
        logger.warning(
            "Received notification for unknown subscription: %s", subscription_id
        )
        return {"status": "ignored", "reason": "unknown_subscription"}

    if entity_type != "AgriParcel":
        return {"status": "ignored", "reason": "wrong_entity_type"}

    if not data:
        return {"status": "ignored", "reason": "no_data"}

    tenant_id = request.headers.get("NGSILD-Tenant") or request.headers.get(
        "Fiware-Service", "default"
    )

    results = []
    for entity in data:
        parcel_id = entity.get("id", "").split(":")[-1]
        if not parcel_id:
            continue

        geometry = entity.get("location", {}).get("value")
        if not geometry:
            continue

        version = entity.get("dateModified", {}).get("value", "v1")
        if isinstance(version, datetime):
            version = version.isoformat()

        parcel_hash = _compute_parcel_hash(parcel_id, tenant_id, str(version))

        if await _is_already_processed(parcel_hash):
            results.append({"parcelId": parcel_id, "status": "already_processed"})
            continue

        expanded_geometry = _expand_geometry(geometry, INGESTION_BUFFER_M)

        redis = ArqRedis.from_url(REDIS_URL)
        await redis.enqueue_job(
            "ingest_parcel",
            parcel_id,
            tenant_id,
            expanded_geometry,
            str(version),
        )

        await _mark_processed(parcel_hash)

        results.append({"parcelId": parcel_id, "status": "enqueued"})

    return {"status": "processed", "results": results}


@router.post("/subscriptions/register")
async def register_subscription(tenant_id: str = None):
    subscription = {
        "id": SUBSCRIPTION_ID,
        "type": "Subscription",
        "entities": [{"type": "AgriParcel"}],
        "watchedAttributes": ["location", "dateModified"],
        "notification": {
            "attributes": ["location", "dateModified"],
            "format": "normalized",
            "endpoint": {
                "uri": "http://soil-api-service:8000/v1/soil/webhooks/orion",
                "accept": "application/json",
            },
        },
        "@context": [CONTEXT_URL],
    }

    async with OrionClient(tenant_id) as orion:
        try:
            await orion.create_entity(subscription)
            return {"status": "registered", "subscriptionId": SUBSCRIPTION_ID}
        except Exception as e:
            if "already exists" in str(e).lower():
                return {"status": "already_registered", "subscriptionId": SUBSCRIPTION_ID}
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/subscriptions/status")
@limiter.exempt
async def subscription_status(tenant_id: str = None):
    async with OrionClient(tenant_id) as orion:
        try:
            entity = await orion._client.get(
                f"/ngsi-ld/v1/subscriptions/{SUBSCRIPTION_ID}"
            )
            return {"status": "active", "subscription": entity}
        except Exception:
            return {"status": "not_found", "subscriptionId": SUBSCRIPTION_ID}
