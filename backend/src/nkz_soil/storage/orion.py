"""Orion-LD access — thin adapter over nkz_platform_sdk.OrionClient."""

import asyncio
import contextvars
import logging
from typing import Any

import httpx
from nkz_platform_sdk import OrionClient as SDKOrionClient

from nkz_soil.config import BATCH_CONCURRENCY, CONTEXT_URL, ORION_LD_URL

logger = logging.getLogger(__name__)

_TENANT: contextvars.ContextVar[str | None] = contextvars.ContextVar("soil_tenant", default=None)


def set_current_tenant(tenant_id: str | None):
    return _TENANT.set(tenant_id)


def current_tenant() -> str | None:
    return _TENANT.get()


def parcel_ref_query(parcel_id: str) -> str:
    """NGSI-LD q filter for refAgriParcel (exact URN)."""
    if parcel_id.startswith("urn:"):
        urn = parcel_id
    else:
        urn = f"urn:ngsi-ld:AgriParcel:{parcel_id}"
    return f'refAgriParcel=="{urn}"'


class OrionClient:
    """Tenant-scoped NGSI-LD client delegating to nkz-platform-sdk.

    Extends the SDK with geometry/category query params used by soil providers
    and spatial point lookups. Prefer SDK methods for standard CRUD.
    """

    def __init__(self, tenant_id: str | None = None):
        if not tenant_id:
            raise ValueError("tenant_id is required for OrionClient")
        self.tenant_id = tenant_id
        self._sdk = SDKOrionClient(
            tenant_id,
            base_url=ORION_LD_URL,
            context_url=CONTEXT_URL,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self) -> None:
        await self._sdk.close()

    def _merge_q(self, q: str | None, category: list[str] | None) -> str | None:
        if category:
            cat_filter = ",".join(f'"{c}"' for c in category)
            cat_q = f"category==[{cat_filter}]"
            return cat_q if not q else f"{q};{cat_q}"
        return q

    async def query_entities(
        self,
        type: str,
        category: list[str] | None = None,
        geometry: dict | None = None,
        q: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        merged_q = self._merge_q(q, category)
        if geometry:
            coords = geometry.get("coordinates")
            if coords:
                params: dict[str, str | int] = {"type": type, "limit": limit}
                if merged_q:
                    params["q"] = merged_q
                params["georel"] = "near;maxDistance=50"
                if geometry["type"] == "Point":
                    params["geometry"] = "Point"
                    params["coordinates"] = f"[{coords[0]},{coords[1]}]"
                elif geometry["type"] == "Polygon":
                    flat = [c for point in coords[0] for c in point]
                    params["geometry"] = "Polygon"
                    params["coordinates"] = f"[[{','.join(str(c) for c in flat)}]]"
                resp = await self._sdk._client.get(
                    self._sdk._url("/ngsi-ld/v1/entities"),
                    params=params,
                    headers=self._sdk._headers("application/json"),
                )
                if resp.status_code == 404:
                    return []
                resp.raise_for_status()
                return resp.json()
        return await self._sdk.query_entities(
            type=type,
            q=merged_q,
            limit=limit,
        )

    async def create_entity(self, entity: dict[str, Any]) -> dict[str, Any]:
        return await self._sdk.create_entity(entity)

    async def create_entities_batch(
        self,
        entities: list[dict[str, Any]],
        *,
        chunk_size: int = 50,
        fallback_concurrency: int | None = None,
    ) -> dict[str, Any]:
        """Batch create with Orion entityOperations/create; fall back to concurrent singles."""
        if not entities:
            return {"created": 0, "errors": [], "entity_ids": []}

        concurrency = fallback_concurrency or BATCH_CONCURRENCY
        total_created = 0
        all_errors: list[Any] = []
        all_ids: list[str] = []

        for i in range(0, len(entities), chunk_size):
            chunk = entities[i : i + chunk_size]
            try:
                result = await self._sdk.create_entities_batch(chunk)
                total_created += result.get("created", 0)
                all_errors.extend(result.get("errors", []))
                all_ids.extend(result.get("entity_ids", []))
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in (404, 405, 501):
                    logger.info(
                        "Orion batch create unavailable (%s), using concurrent singles",
                        status,
                    )
                    part = await self._create_chunk_concurrent(chunk, concurrency)
                    total_created += part["created"]
                    all_errors.extend(part["errors"])
                    all_ids.extend(part["entity_ids"])
                else:
                    raise
            except Exception:
                logger.warning("Orion batch create failed, using concurrent singles", exc_info=True)
                part = await self._create_chunk_concurrent(chunk, concurrency)
                total_created += part["created"]
                all_errors.extend(part["errors"])
                all_ids.extend(part["entity_ids"])

        return {
            "created": total_created,
            "errors": all_errors,
            "entity_ids": all_ids,
        }

    async def _create_chunk_concurrent(
        self,
        entities: list[dict[str, Any]],
        concurrency: int,
    ) -> dict[str, Any]:
        sem = asyncio.Semaphore(concurrency)
        errors: list[dict[str, str]] = []
        created_ids: list[str] = []

        async def _one(entity: dict[str, Any]) -> None:
            async with sem:
                try:
                    out = await self._sdk.create_entity(entity)
                    eid = out.get("id") or entity.get("id", "")
                    if eid:
                        created_ids.append(eid)
                except Exception as exc:
                    errors.append({"id": entity.get("id", ""), "error": str(exc)})

        await asyncio.gather(*[_one(e) for e in entities])
        return {
            "created": len(created_ids),
            "errors": errors,
            "entity_ids": created_ids,
        }

    async def patch_entity(self, entity_id: str, attrs: dict[str, Any]) -> None:
        await self._sdk.update_entity_attrs(entity_id, attrs)

    async def delete_entity(self, entity_id: str) -> None:
        await self._sdk.delete_entity(entity_id)

    async def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        resp = await self._sdk._client.get(
            self._sdk._url(f"/ngsi-ld/v1/subscriptions/{subscription_id}"),
            headers=self._sdk._headers("application/json"),
        )
        resp.raise_for_status()
        return resp.json()
