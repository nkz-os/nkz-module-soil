import contextvars
import os

import httpx

from nkz_soil.config import CONTEXT_URL

_TENANT: contextvars.ContextVar[str | None] = contextvars.ContextVar("soil_tenant", default=None)


def set_current_tenant(tenant_id: str | None):
    return _TENANT.set(tenant_id)


def current_tenant() -> str | None:
    return _TENANT.get()


ORION_LD_URL = os.getenv("ORION_LD_URL", "http://orion-ld-service:1026")


class OrionClient:
    """NGSI-LD client with tenant-scoped queries, geometry filtering, and strict
    FIWARE header injection.

    Uses httpx directly instead of wrapping nkz-platform-sdk's OrionClient,
    whose API changed significantly across versions (v0.1 generic get/post vs
    v0.3 typed query_entities/create_entity).
    """

    def __init__(self, tenant_id: str | None = None):
        self.tenant_id = tenant_id
        self._client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    def _headers(self, content_type: str = "application/json") -> dict[str, str]:
        h: dict[str, str] = {}
        if self.tenant_id:
            h["NGSILD-Tenant"] = self.tenant_id
            h["Fiware-Service"] = self.tenant_id
            h["Fiware-ServicePath"] = "/"
        if content_type == "application/ld+json":
            h["Content-Type"] = "application/ld+json"
        elif content_type == "application/json":
            h["Content-Type"] = "application/json"
            h["Link"] = (
                f'<{CONTEXT_URL}>; rel="http://www.w3.org/ns/json-ld#context";'
                ' type="application/ld+json"'
            )
        return h

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
        resp = await self._client.get(
            f"{ORION_LD_URL}/ngsi-ld/v1/entities{query}",
            headers=self._headers("application/json"),
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json()

    async def create_entity(self, entity: dict) -> dict:
        if "@context" not in entity:
            entity["@context"] = [CONTEXT_URL]
        resp = await self._client.post(
            f"{ORION_LD_URL}/ngsi-ld/v1/entities",
            json=entity,
            headers=self._headers("application/ld+json"),
        )
        resp.raise_for_status()
        location = resp.headers.get("Location", "")
        return {"id": location.split("/")[-1] if location else "", "status": "created"}

    async def patch_entity(self, entity_id: str, attrs: dict) -> None:
        resp = await self._client.patch(
            f"{ORION_LD_URL}/ngsi-ld/v1/entities/{entity_id}/attrs",
            json=attrs,
            headers=self._headers("application/ld+json"),
        )
        resp.raise_for_status()

    async def delete_entity(self, entity_id: str) -> None:
        resp = await self._client.delete(
            f"{ORION_LD_URL}/ngsi-ld/v1/entities/{entity_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
