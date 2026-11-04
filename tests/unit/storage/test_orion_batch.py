"""Tests for Orion batch create with fallback."""

import pytest
import respx
from httpx import Response
from nkz_soil.storage.orion import OrionClient


@pytest.mark.asyncio
@respx.mock
async def test_create_entities_batch_success():
    respx.post("http://localhost:1026/ngsi-ld/v1/entityOperations/create").mock(
        return_value=Response(201, json={})
    )
    async with OrionClient("tenant1") as orion:
        result = await orion.create_entities_batch([
            {
                "id": "urn:ngsi-ld:SoilSamplingPoint:a",
                "type": "SoilSamplingPoint",
            },
        ])
    assert result["created"] == 1
    assert result["entity_ids"] == ["urn:ngsi-ld:SoilSamplingPoint:a"]


@pytest.mark.asyncio
@respx.mock
async def test_create_entities_batch_fallback_on_501():
    respx.post("http://localhost:1026/ngsi-ld/v1/entityOperations/create").mock(
        return_value=Response(501, text="not supported")
    )
    respx.post("http://localhost:1026/ngsi-ld/v1/entities").mock(
        return_value=Response(201, headers={"Location": "/ngsi-ld/v1/entities/urn:ngsi-ld:SoilSamplingPoint:b"})
    )
    async with OrionClient("tenant1") as orion:
        result = await orion.create_entities_batch([
            {
                "id": "urn:ngsi-ld:SoilSamplingPoint:b",
                "type": "SoilSamplingPoint",
            },
        ])
    assert result["created"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_upsert_entities_batch_chunks_and_collects_errors():
    calls = []

    def _reply(request):
        import json as _json
        batch = _json.loads(request.content)
        calls.append(len(batch))
        if len(calls) == 2:  # second chunk: one entity refused
            return Response(207, json={"success": [batch[0]["id"]],
                                       "errors": [{"entityId": batch[1]["id"], "error": {"title": "x"}}]})
        return Response(204)

    route = respx.post("http://localhost:1026/ngsi-ld/v1/entityOperations/upsert").mock(side_effect=_reply)
    ents = [{"id": f"urn:ngsi-ld:AgriSoilSample:tenant1:{i}", "type": "AgriSoilSample"} for i in range(4)]
    async with OrionClient("tenant1") as orion:
        result = await orion.upsert_entities_batch(ents, chunk_size=2)
    assert calls == [2, 2]
    assert route.calls[0].request.url.params["options"] == "update"
    assert result["upserted"] == 3 and len(result["errors"]) == 1
    assert result["entity_ids"] == [e["id"] for e in ents[:3]]


@pytest.mark.asyncio
@respx.mock
async def test_query_all_pages_through_the_broker_limit():
    calls = []

    def _reply(request):
        off = int(request.url.params["offset"])
        calls.append(off)
        n = 1000 if off == 0 else 3
        return Response(200, json=[{"id": f"urn:ngsi-ld:AgriPlant:t:{off + i}"} for i in range(n)])

    respx.get("http://localhost:1026/ngsi-ld/v1/entities").mock(side_effect=_reply)
    async with OrionClient("tenant1") as orion:
        out = await orion.query_all("AgriPlant", q='hasAgriParcel=="urn:ngsi-ld:AgriParcel:p"')
    assert calls == [0, 1000] and len(out) == 1003
