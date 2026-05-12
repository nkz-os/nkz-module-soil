try:
    from nkz_platform_sdk import OrionClient as SDKOrionClient
except ImportError:
    SDKOrionClient = None


class OrionClient:
    """Wrapper around nkz-platform-sdk OrionClient with soil-specific queries."""

    def __init__(self, tenant_id: str | None = None):
        if SDKOrionClient is None:
            raise ImportError("nkz-platform-sdk is required for OrionClient")
        self._client = SDKOrionClient(tenant_id=tenant_id)

    async def __aenter__(self):
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self._client.__aexit__(*args)

    async def query_entities(self, type: str, category: list[str] | None = None,
                              geometry: dict | None = None) -> list[dict]:
        """Query NGSI-LD entities by type, optional category filter, and geometry."""
        query = f'?type={type}'
        if category:
            cat_filter = ",".join(f'"{c}"' for c in category)
            query += f'&q=category==[{cat_filter}]'
        if geometry:
            coords = geometry.get("coordinates")
            if coords:
                query += f'&georel=near;maxDistance=50'
                if geometry["type"] == "Point":
                    query += f'&geometry=Point&coordinates=[{coords[0]},{coords[1]}]'
        return await self._client.get(f'/ngsi-ld/v1/entities{query}')

    async def create_entity(self, entity: dict) -> dict:
        return await self._client.post('/ngsi-ld/v1/entities', json=entity)

    async def patch_entity(self, entity_id: str, attrs: dict) -> None:
        await self._client.patch(f'/ngsi-ld/v1/entities/{entity_id}/attrs', json=attrs)

    async def delete_entity(self, entity_id: str) -> None:
        await self._client.delete(f'/ngsi-ld/v1/entities/{entity_id}')
