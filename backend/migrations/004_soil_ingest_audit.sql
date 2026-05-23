-- migrations/004_soil_ingest_audit.sql
-- Per-ingest audit log: which provider, which parcel, latency, source versions.

CREATE TABLE IF NOT EXISTS soil_module.soil_ingest_audit (
    audit_id     BIGSERIAL PRIMARY KEY,
    parcel_id    TEXT NOT NULL,
    provider     VARCHAR(64) NOT NULL,
    status       VARCHAR(16) NOT NULL,           -- 'ok' | 'no-data' | 'circuit-open' | 'error'
    latency_ms   INTEGER,
    source_tag   VARCHAR(128),
    source_version VARCHAR(64),
    error_text   TEXT,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS soil_ingest_audit_parcel_ix
    ON soil_module.soil_ingest_audit (parcel_id, ingested_at DESC);
CREATE INDEX IF NOT EXISTS soil_ingest_audit_provider_ix
    ON soil_module.soil_ingest_audit (provider, ingested_at DESC);
