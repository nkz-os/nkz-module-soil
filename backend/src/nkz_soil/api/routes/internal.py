"""Internal service-to-service endpoints (bypass JWT, authenticated by shared secret).

These routes are registered WITHOUT the global JWT middleware. They are
protected only by X-Internal-Service-Secret validation.

This module is registered in main.py BEFORE the require_auth middleware is applied.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from nkz_soil.api.dependencies import get_redis_pool
from nkz_soil.config import INTERNAL_SERVICE_SECRET
from nkz_soil.storage.orion import OrionClient

logger = logging.getLogger(__name__)

_PARCEL_URN_PREFIX = "urn:ngsi-ld:AgriParcel:"


def _parcel_urn(parcel_id: str) -> str:
    if parcel_id.startswith(_PARCEL_URN_PREFIX):
        return parcel_id
    return f"{_PARCEL_URN_PREFIX}{parcel_id}"

router = APIRouter()


def _validate_internal_secret(request: Request) -> None:
    """Raise 403 if X-Internal-Service-Secret is missing or wrong."""
    if not INTERNAL_SERVICE_SECRET:
        logger.warning("INTERNAL_SERVICE_SECRET not configured — internal endpoints disabled")
        raise HTTPException(status_code=503, detail="Internal auth not configured")
    provided = request.headers.get("X-Internal-Service-Secret", "")
    if provided != INTERNAL_SERVICE_SECRET:
        raise HTTPException(status_code=403, detail="Invalid internal service secret")


@router.post("/setup-parcel", status_code=202)
async def setup_parcel(request: Request):
    """Trigger soil ingest for a parcel.

    Called by entity-manager during module parcel activation flow.
    Idempotent: uses same dedup hash as the Orion webhook.

    Headers: X-Internal-Service-Secret (required)
    Body: { parcel_id, tenant_id, geometry? }
    """
    _validate_internal_secret(request)

    body = await request.json()
    parcel_id = (body.get("parcel_id") or "").strip()
    tenant_id = (body.get("tenant_id") or "").strip()
    geometry = body.get("geometry") or {}

    if not parcel_id or not tenant_id:
        raise HTTPException(status_code=422, detail="parcel_id and tenant_id are required")

    # If no geometry provided, resolve from Orion. `id` is not a queryable
    # attribute in NGSI-LD's `q` grammar — a `q='id=="..."'` filter always
    # returns zero results — so fetch the entity directly by id instead.
    if not geometry:
        async with OrionClient(tenant_id) as orion:
            entity = await orion.get_entity(_parcel_urn(parcel_id))
            if entity:
                geometry = entity.get("location", {}).get("value", {})
        if not geometry:
            raise HTTPException(
                status_code=404,
                detail=f"Cannot resolve geometry for parcel {parcel_id}",
            )

    from nkz_soil.api.routes.subscriptions import expand_geometry
    from nkz_soil.config import INGESTION_BUFFER_M

    expanded_geometry = expand_geometry(geometry, INGESTION_BUFFER_M)

    redis = get_redis_pool(request)
    await redis.enqueue_job(
        "ingest_parcel",
        parcel_id,
        tenant_id,
        expanded_geometry,
        "v1",  # parcel_version — not known at activation time; webhook will re-ingest on update
    )

    return {"status": "accepted", "parcelId": parcel_id}
