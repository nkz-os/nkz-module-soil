"""Tenant discovery must query the platform DB (where tenant_installed_modules
lives), not the soil module's own DB. Mirrors weather-map's discover pattern."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def test_platform_postgres_url_prefers_full_url(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgresql://u:p@h:5432/db")
    from nkz_soil.workers.ingest import _platform_postgres_url
    assert _platform_postgres_url() == "postgresql://u:p@h:5432/db"


def test_platform_postgres_url_built_from_parts(monkeypatch):
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "postgresql-service")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "nekazari")
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    from nkz_soil.workers.ingest import _platform_postgres_url
    assert (
        _platform_postgres_url()
        == "postgresql://postgres:secret@postgresql-service:5432/nekazari"
    )


def test_platform_postgres_url_empty_without_credentials(monkeypatch):
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    from nkz_soil.workers.ingest import _platform_postgres_url
    # No password → cannot build a platform DSN → empty (caller falls back).
    assert _platform_postgres_url() == ""


@pytest.mark.asyncio
async def test_backfill_uses_orionclient_when_tenants_found_in_db(monkeypatch):
    """When tenants come from the platform DB, the Orion-scan block is skipped.

    A function-local `import OrionClient` inside that block used to shadow the
    module-level name for the whole function, so the main loop raised
    UnboundLocalError once DB discovery actually returned tenants.
    """
    monkeypatch.setenv("POSTGRES_URL", "postgresql://u:p@h:5432/nekazari")

    # asyncpg.connect -> conn.fetch returns one enabled soil tenant
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"tenant_id": "montiko"}])
    conn.close = AsyncMock()

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

    import asyncpg
    from nkz_soil.workers.ingest import backfill_parcels_without_soil

    with patch.object(asyncpg, "connect", AsyncMock(return_value=conn)), \
         patch("nkz_soil.workers.ingest.OrionClient", return_value=orion):
        await backfill_parcels_without_soil({"redis": redis})

    redis.enqueue_job.assert_awaited_once()
    args = redis.enqueue_job.call_args[0]
    assert args[0] == "ingest_parcel"
    assert args[1] == "p1"
    assert args[2] == "montiko"
