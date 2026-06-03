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
