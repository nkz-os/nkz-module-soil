"""Tenant discovery must query the platform DB (where tenant_installed_modules
lives), not the soil module's own DB. Mirrors weather-map's discover pattern."""
from __future__ import annotations


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
