import contextvars

try:
    from nkz_platform_sdk import OrionClient as SDKOrionClient
except ImportError:
    SDKOrionClient = None

from nkz_soil.config import CONTEXT_URL

_TENANT: contextvars.ContextVar[str | None] = contextvars.ContextVar("soil_tenant", default=None)


def set_current_tenant(tenant_id: str | None):
    return _TENANT.set(tenant_id)


def current_tenant() -> str | None:
    return _TENANT.get()


class OrionClient:
    """Wrapper around nkz-platform-sdk OrionClient with soil-specific queries.

    Enforces NGSI-LD strict mode:
    - application/ld+json: @context embedded in body
    - application/json: Link header with context URL
    """

    def __init__(self, tenant_id: str | None = None):
        if SDKOrionClient is None:
            raise ImportError("nkz-platform-sdk is required for OrionClient")
        self._client = SDKOrionClient(tenant_id=tenant_id)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.close()

    async def query_entities(
        self,
        type: str,
        category: list[str] | None = None,
        geometry: dict | None = None,
    ) -> list[dict]:
        query = f"?type={type}"
        if category:
            cat_filter = ",".join(f'"{c}"' for c in category)
            query += f"&q=category==[{cat_filter}]"
        if geometry:
            coords = geometry.get("coordinates")
            if coords:
                query += "&georel=near;maxDistance=50"
                if geometry["type"] == "Point":
                    query += f"&geometry=Point&coordinates=[{coords[0]},{coords[1]}]"
                elif geometry["type"] == "Polygon":
                    flat = [c for point in coords[0] for c in point]
                    query += f"&geometry=Polygon&coordinates=[[{','.join(str(c) for c in flat)}]]"
        return await self._client.get(f"/ngsi-ld/v1/entities{query}")

    async def create_entity(self, entity: dict) -> dict:
        if "@context" not in entity:
            entity["@context"] = [CONTEXT_URL]
        return await self._client.post("/ngsi-ld/v1/entities", json=entity)

    async def patch_entity(self, entity_id: str, attrs: dict) -> None:
        await self._client.patch(
            f"/ngsi-ld/v1/entities/{entity_id}/attrs", json=attrs
        )

    async def delete_entity(self, entity_id: str) -> None:
        await self._client.delete(f"/ngsi-ld/v1/entities/{entity_id}")
