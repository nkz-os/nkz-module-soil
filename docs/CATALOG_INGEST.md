# PostgreSQL catalog ingest (LUCAS / ESDB)

## Scope

This module uses **two data planes**:

| Plane | Storage | Use |
|-------|---------|-----|
| Tenant operational | Orion-LD (`AgriSoilExtended`, `SoilSamplingPoint`, …) | Runtime API, worker ingest, subscriptions |
| Reference catalog | PostgreSQL schema `soil_module` | LUCAS topsoil, ESDB rasters, texture indexes |

Platform rule *“zero direct DB writes from workers/APIs”* applies to **tenant business data**. Catalog loaders are **bootstrap / ETL** jobs, not tenant CRUD.

## Loader entry points

| Script | Tables | When to run |
|--------|--------|-------------|
| `backend/src/nkz_soil/ingest/lucas_loader.py` | `lucas_topsoil_2018` | After obtaining LUCAS CSV |
| `backend/src/nkz_soil/ingest/lucas_aux_loader.py` | bulk density, erosion, organic | Optional LUCAS aux |
| `backend/src/nkz_soil/ingest/lucas_texture_loader.py` | `lucas_texture_raster_index` | After raster upload to MinIO |
| `backend/src/nkz_soil/ingest/esdb_raster_loader.py` | `esdb_raster_index` | After ESDB COG ingest |
| `backend/scripts/run_migrations.py` | DDL + SQL migrations | `k8s/job-soil-migrate.yaml` |

All loaders use idempotent `INSERT … ON CONFLICT DO UPDATE`.

## What must NOT write PostgreSQL

- FastAPI routes under `backend/src/nkz_soil/api/`
- `backend/src/nkz_soil/workers/ingest.py` (parcel ingest → Orion-LD only)
- Provider `fetch()` paths during tenant requests

Providers may **read** `soil_module` tables (e.g. LUCAS KNN index) — read-only SQL is allowed.

## Audit wording

> Catalog/reference ingestion into `soil_module` PostgreSQL is intentional. Tenant-facing soil state lives in Orion-LD. Runtime services must not INSERT/UPDATE tenant rows in PostgreSQL.

See also: `internal-docs-local/modules/soil/2026-06-03-soil-hardening-backlog.md` (section 4).
