"""Integration tests against real Orion-LD.

These tests require a running Orion-LD instance and are skipped
if the required environment variables are not set.

Usage:
    ORION_BASE_URL=http://orion:1026 CONTEXT_URL=http://gateway:5000/ngsi-ld-context.json \
    REDIS_URL=redis://redis:6379 \
    pytest tests/integration/ -v
"""

import os
import uuid

import pytest

# Skip all integration tests if env vars are missing
ORION_URL = os.environ.get("ORION_BASE_URL")
CONTEXT_URL = os.environ.get("CONTEXT_URL")
REDIS_URL = os.environ.get("REDIS_URL")

pytestmark = pytest.mark.skipif(
    not (ORION_URL and CONTEXT_URL),
    reason="Integration tests require ORION_BASE_URL and CONTEXT_URL env vars",
)


@pytest.fixture
def tenant_id():
    """Use a unique tenant for each test run to avoid cross-test pollution."""
    return f"test-soil-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cleanup_entities(tenant_id):
    """Clean up test entities after each test."""
    from nkz_soil.storage.orion import OrionClient

    created_ids = []
    yield created_ids

    # Cleanup
    import asyncio

    async def _cleanup():
        async with OrionClient(tenant_id) as orion:
            for entity_id in created_ids:
                try:
                    await orion.delete_entity(entity_id)
                except Exception:
                    pass

    asyncio.run(_cleanup())


@pytest.mark.asyncio
async def test_create_and_query_soil_sampling_point(tenant_id, cleanup_entities):
    """Create a SoilSamplingPoint in Orion and verify it can be queried."""
    from nkz_soil.storage.orion import OrionClient

    entity_id = f"urn:ngsi-ld:SoilSamplingPoint:{uuid.uuid4()}"
    entity = {
        "id": entity_id,
        "type": "SoilSamplingPoint",
        "@context": [CONTEXT_URL],
        "location": {
            "type": "GeoProperty",
            "value": {"type": "Point", "coordinates": [-1.6, 42.8]},
        },
        "samplingDate": {"type": "Property", "value": "2026-05-20"},
        "horizons": {
            "type": "Property",
            "value": [
                {
                    "depthFrom": 0,
                    "depthTo": 30,
                    "sand": 45.0,
                    "silt": 35.0,
                    "clay": 20.0,
                    "ph": 6.8,
                }
            ],
        },
    }

    async with OrionClient(tenant_id) as orion:
        await orion.create_entity(entity)
        cleanup_ids = cleanup_entities
        if isinstance(cleanup_ids, list):
            cleanup_ids.append(entity_id)

        # Query back
        entities = await orion.query_entities(type="SoilSamplingPoint")
        matching = [e for e in entities if e.get("id") == entity_id]
        assert len(matching) == 1
        assert matching[0]["horizons"]["value"][0]["sand"] == 45.0


@pytest.mark.asyncio
async def test_create_and_query_agri_soil(tenant_id, cleanup_entities):
    """Create an AgriSoil entity and verify query by type."""
    from nkz_soil.storage.orion import OrionClient

    parcel_id = f"test-parcel-{uuid.uuid4().hex[:8]}"
    entity_id = f"urn:ngsi-ld:AgriSoil:{tenant_id}:{parcel_id}"
    entity = {
        "id": entity_id,
        "type": "AgriSoil",
        "@context": [CONTEXT_URL],
        "location": {
            "type": "GeoProperty",
            "value": {
                "type": "Polygon",
                "coordinates": [[
                    [-2.0, 42.0], [-1.0, 42.0], [-1.0, 43.0], [-2.0, 43.0], [-2.0, 42.0]
                ]],
            },
        },
        "refAgriParcel": {
            "type": "Relationship",
            "object": f"urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}",
        },
        "parcelVersionId": {"type": "Property", "value": "v1"},
        "horizons": {
            "type": "Property",
            "value": [
                {
                    "depthFrom": 0,
                    "depthTo": 5,
                    "sand": 50.0,
                    "silt": 30.0,
                    "clay": 20.0,
                    "ksatSaturated": 12.5,
                    "hydrologicGroup": "B",
                },
                {
                    "depthFrom": 5,
                    "depthTo": 15,
                    "sand": 45.0,
                    "silt": 35.0,
                    "clay": 20.0,
                    "ksatSaturated": 8.3,
                    "hydrologicGroup": "B",
                },
            ],
        },
        "dataSource": {"type": "Property", "value": "lab_analysis"},
        "uncertainty": {"type": "Property", "value": 0.05},
        "lastUpdated": {"type": "Property", "value": "2026-05-20T00:00:00Z"},
    }

    async with OrionClient(tenant_id) as orion:
        await orion.create_entity(entity)
        cleanup_ids = cleanup_entities
        if isinstance(cleanup_ids, list):
            cleanup_ids.append(entity_id)

        # Query back
        entities = await orion.query_entities(type="AgriSoil")
        matching = [e for e in entities if e.get("id") == entity_id]
        assert len(matching) == 1
        assert matching[0]["dataSource"]["value"] == "lab_analysis"
        assert len(matching[0]["horizons"]["value"]) == 2


@pytest.mark.asyncio
async def test_patch_agri_soil(tenant_id, cleanup_entities):
    """Patch an existing AgriSoil entity and verify the update."""
    from nkz_soil.storage.orion import OrionClient

    parcel_id = f"test-patch-{uuid.uuid4().hex[:8]}"
    entity_id = f"urn:ngsi-ld:AgriSoil:{tenant_id}:{parcel_id}"

    # Create
    async with OrionClient(tenant_id) as orion:
        await orion.create_entity({
            "id": entity_id,
            "type": "AgriSoil",
            "@context": [CONTEXT_URL],
            "location": {
                "type": "GeoProperty",
                "value": {"type": "Point", "coordinates": [-1.6, 42.8]},
            },
            "refAgriParcel": {
                "type": "Relationship",
                "object": f"urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}",
            },
            "parcelVersionId": {"type": "Property", "value": "v1"},
            "horizons": {"type": "Property", "value": []},
            "dataSource": {"type": "Property", "value": "soilgrids"},
            "uncertainty": {"type": "Property", "value": 0.25},
            "lastUpdated": {"type": "Property", "value": "2026-05-20"},
        })
        cleanup_ids = cleanup_entities
        if isinstance(cleanup_ids, list):
            cleanup_ids.append(entity_id)

        # Patch
        await orion.patch_entity(entity_id, {
            "dataSource": {"type": "Property", "value": "idena"},
            "uncertainty": {"type": "Property", "value": 0.10},
        })

        # Verify
        entities = await orion.query_entities(type="AgriSoil")
        matching = [e for e in entities if e.get("id") == entity_id]
        assert len(matching) == 1
        assert matching[0]["dataSource"]["value"] == "idena"
        assert matching[0]["uncertainty"]["value"] == 0.10
