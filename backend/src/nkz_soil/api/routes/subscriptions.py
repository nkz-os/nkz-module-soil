import hashlib
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from nkz_platform_sdk import AuthContext
from nkz_soil.api.dependencies import get_redis_pool, require_auth
from nkz_soil.api.limiter import limiter
from nkz_soil.config import CONTEXT_URL, INGESTION_BUFFER_M, ORION_WEBHOOK_SECRET, SOIL_INGEST_TTL
from nkz_soil.storage.orion import OrionClient

logger = logging.getLogger(__name__)

router = APIRouter()

SUBSCRIPTION_ID = "urn:ngsi-ld:Subscription:soil-parcel-ingest"


class OrionNotification(BaseModel):
    id: str
    type: str
    subscriptionId: str
    data: list[dict] | None = None


def _compute_parcel_hash(parcel_id: str, tenant_id: str, version: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{parcel_id}:{version}".encode()).hexdigest()[:16]


def _resolve_webhook_tenant(request: Request) -> str:
    tenant_id = (
        request.headers.get("NGSILD-Tenant")
        or request.headers.get("Fiware-Service")
        or ""
    ).strip()
    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="Missing NGSILD-Tenant or Fiware-Service header",
        )
    return tenant_id


def _validate_webhook_secret(request: Request) -> None:
    if not ORION_WEBHOOK_SECRET:
        return
    provided = request.headers.get("X-Orion-Webhook-Secret", "")
    if provided != ORION_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")


async def _is_already_processed(redis, parcel_hash: str) -> bool:
    key = f"soil:ingested:{parcel_hash}"
    return await redis.exists(key) == 1


async def _mark_processed(redis, parcel_hash: str) -> None:
    key = f"soil:ingested:{parcel_hash}"
    await redis.set(key, datetime.now(timezone.utc).isoformat(), ex=SOIL_INGEST_TTL)


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


# Public alias for cross-module use (internal route, etc.)
expand_geometry = _expand_geometry


@router.post("/webhooks/orion")
@limiter.exempt
async def orion_webhook(request: Request):
    _validate_webhook_secret(request)
    body = await request.json()

    subscription_id = body.get("subscriptionId", "")
    entity_type = body.get("type", "")
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

    tenant_id = _resolve_webhook_tenant(request)
    redis = get_redis_pool(request)

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

        if await _is_already_processed(redis, parcel_hash):
            results.append({"parcelId": parcel_id, "status": "already_processed"})
            continue

        expanded_geometry = _expand_geometry(geometry, INGESTION_BUFFER_M)

        await redis.enqueue_job(
            "ingest_parcel",
            parcel_id,
            tenant_id,
            expanded_geometry,
            str(version),
        )

        await _mark_processed(redis, parcel_hash)

        results.append({"parcelId": parcel_id, "status": "enqueued"})

    return {"status": "processed", "results": results}


@router.post("/subscriptions/register")
async def register_subscription(auth: AuthContext = require_auth(roles=["GestorAgricola", "Administrador"])):
    subscription = {
        "id": SUBSCRIPTION_ID,
        "type": "Subscription",
        "entities": [{"type": "AgriParcel"}],
        "watchedAttributes": ["location", "dateModified"],
        "notification": {
            "attributes": ["location", "dateModified"],
            "format": "normalized",
            "endpoint": {
                "uri": "http://soil-module-service:8000/v1/soil/webhooks/orion",
                "accept": "application/json",
            },
        },
        "@context": [CONTEXT_URL],
    }

    async with OrionClient(auth.tenant_id) as orion:
        try:
            await orion.create_entity(subscription)
            return {"status": "registered", "subscriptionId": SUBSCRIPTION_ID}
        except Exception as e:
            if "already exists" in str(e).lower():
                return {"status": "already_registered", "subscriptionId": SUBSCRIPTION_ID}
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/subscriptions/status")
@limiter.exempt
async def subscription_status(auth: AuthContext = require_auth(roles=["GestorAgricola", "Administrador"])):
    async with OrionClient(auth.tenant_id) as orion:
        try:
            entity = await orion.get_subscription(SUBSCRIPTION_ID)
            return {"status": "active", "subscription": entity}
        except Exception:
            return {"status": "not_found", "subscriptionId": SUBSCRIPTION_ID}
