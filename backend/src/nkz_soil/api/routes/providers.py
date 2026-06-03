from fastapi import APIRouter

from nkz_platform_sdk import AuthContext
from nkz_soil.api.dependencies import require_auth
from nkz_soil.api.limiter import limiter
from nkz_soil.providers.base import ProviderRegistry

router = APIRouter()

_registry: ProviderRegistry | None = None


def set_registry(registry: ProviderRegistry):
    global _registry
    _registry = registry


@router.get("/providers/health")
@limiter.exempt
async def provider_health(auth: AuthContext = require_auth()):
    if not _registry:
        return {"providers": []}
    results = []
    for p in _registry.get_all():
        try:
            health = await p.health()
            results.append(
                {
                    "name": p.name,
                    "status": health.status,
                    "latency_ms": health.latency_ms,
                }
            )
        except Exception:
            results.append({"name": p.name, "status": "down", "latency_ms": 0})
    return {"providers": results}


@router.get("/providers/coverage")
@limiter.exempt
async def provider_coverage(bbox: str, auth: AuthContext = require_auth()):
    coords = [float(c) for c in bbox.split(",")]
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [coords[0], coords[1]],
                [coords[2], coords[1]],
                [coords[2], coords[3]],
                [coords[0], coords[3]],
                [coords[0], coords[1]],
            ]
        ],
    }
    if not _registry:
        return {"providers": []}
    results = []
    for p in _registry.get_all():
        if p.covers(geometry):
            results.append({"name": p.name, "priority": p.priority})
    return {"providers": results}
