"""Tenant discovery asks the platform where the soil module is enabled (internal
API through the SDK) and falls back to SOIL_ENABLED_TENANTS; it never reads the
platform database."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from nkz_platform_sdk.installations import InstalledTenantsUnavailable, TenantInstallations


def _installed(*enabled, disabled=(), not_installed=()):
    return AsyncMock(
        return_value=TenantInstallations("soil", tuple(enabled), tuple(disabled), tuple(not_installed))
    )


def _unavailable():
    return AsyncMock(side_effect=InstalledTenantsUnavailable("soil: down"))


@pytest.mark.asyncio
async def test_backfill_uses_orionclient_when_tenants_found_on_the_platform(monkeypatch):
    """When tenants come from the platform, the Orion-scan block is skipped.

    A function-local `import OrionClient` inside that block used to shadow the
    module-level name for the whole function, so the main loop raised
    UnboundLocalError once DB discovery actually returned tenants.
    """

    # OrionClient: one parcel without soil → must enqueue one ingest job
    orion = AsyncMock()
    orion.__aenter__ = AsyncMock(return_value=orion)
    orion.__aexit__ = AsyncMock(return_value=None)
    orion.query_entities = AsyncMock(side_effect=[
        [{"id": "urn:ngsi-ld:AgriParcel:p1", "location": {"value": {"type": "Point", "coordinates": [0, 0]}}}],
        [],  # no AgriSoilExtended yet
    ])

    redis = AsyncMock()
    redis.enqueue_job = AsyncMock()

    from nkz_soil.workers.ingest import backfill_parcels_without_soil

    with patch("nkz_soil.workers.ingest.installed_tenants", _installed("acmefarm")), \
         patch("nkz_soil.workers.ingest.OrionClient", return_value=orion):
        await backfill_parcels_without_soil({"redis": redis})

    redis.enqueue_job.assert_awaited_once()
    args = redis.enqueue_job.call_args[0]
    assert args[0] == "ingest_parcel"
    assert args[1] == "p1"
    assert args[2] == "acmefarm"


@pytest.mark.asyncio
async def test_backfill_skips_parcels_whose_soil_comes_back_as_refagriparcel(monkeypatch):
    """Orion compacts the relationship to the legacy alias refAgriParcel.

    Reading only hasAgriParcel left the "already has soil" set empty, so every
    parcel was re-ingested on every run (seen live 2026-10-09: 19 enqueued).
    """
    orion = AsyncMock()
    orion.__aenter__ = AsyncMock(return_value=orion)
    orion.__aexit__ = AsyncMock(return_value=None)
    orion.query_entities = AsyncMock(side_effect=[
        [{"id": "urn:ngsi-ld:AgriParcel:p1", "location": {"value": {}}},
         {"id": "urn:ngsi-ld:AgriParcel:p2", "location": {"value": {}}}],
        [{"id": "urn:ngsi-ld:AgriSoilExtended:p1",
          "refAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:p1"}}],
    ])
    redis = AsyncMock()
    redis.enqueue_job = AsyncMock()

    from nkz_soil.workers.ingest import backfill_parcels_without_soil

    with patch("nkz_soil.workers.ingest.installed_tenants", _installed("acmefarm")), \
         patch("nkz_soil.workers.ingest.OrionClient", return_value=orion):
        await backfill_parcels_without_soil({"redis": redis})

    redis.enqueue_job.assert_awaited_once()
    assert redis.enqueue_job.call_args[0][1] == "p2"


@pytest.mark.asyncio
async def test_no_tenants_without_platform_or_env_and_no_guessing(monkeypatch):
    """Without the platform answer and SOIL_ENABLED_TENANTS there is nothing to scan:
    no hardcoded tenant names are probed in Orion."""
    monkeypatch.delenv("SOIL_ENABLED_TENANTS", raising=False)
    import logging

    from nkz_soil.workers.ingest import _soil_tenants

    with patch("nkz_soil.workers.ingest.installed_tenants", _unavailable()), \
         patch("nkz_soil.workers.ingest.OrionClient") as orion:
        tenants = await _soil_tenants(logging.getLogger("test"))
    assert tenants == []
    orion.assert_not_called()


@pytest.mark.asyncio
async def test_tenants_from_env_when_platform_unavailable(monkeypatch):
    monkeypatch.setenv("SOIL_ENABLED_TENANTS", "t1, t2")
    import logging

    from nkz_soil.workers.ingest import _soil_tenants

    with patch("nkz_soil.workers.ingest.installed_tenants", _unavailable()):
        assert await _soil_tenants(logging.getLogger("test")) == ["t1", "t2"]


@pytest.mark.asyncio
async def test_only_enabled_tenants_of_the_soil_module(monkeypatch):
    monkeypatch.setenv("SOIL_ENABLED_TENANTS", "env-tenant")
    import logging

    from nkz_soil.workers.ingest import _soil_tenants

    lookup = _installed("tenant-a", "tenant-b", disabled=("tenant-c",), not_installed=("tenant-d",))
    with patch("nkz_soil.workers.ingest.installed_tenants", lookup):
        assert await _soil_tenants(logging.getLogger("test")) == ["tenant-a", "tenant-b"]
    lookup.assert_awaited_once_with("soil")
