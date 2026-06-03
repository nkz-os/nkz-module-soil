"""Gateway auth dependencies — JWT is validated by api-gateway, not here."""

from fastapi import Request
from nkz_platform_sdk import AuthContext, require_auth


def gateway_auth_headers(
    tenant_id: str = "tenant1",
    user_id: str = "test-user",
    roles: str = "GestorAgricola",
) -> dict[str, str]:
    """Headers simulating api-gateway injection (for tests and local curl)."""
    return {
        "X-Tenant-ID": tenant_id,
        "X-User-ID": user_id,
        "X-User-Roles": roles,
    }


def get_redis_pool(request: Request):
    """Shared ArqRedis pool created in FastAPI lifespan."""
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise RuntimeError("Redis pool not initialized — app lifespan not started")
    return redis


__all__ = ["AuthContext", "require_auth", "gateway_auth_headers", "get_redis_pool"]
