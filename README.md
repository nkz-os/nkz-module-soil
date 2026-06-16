# nkz-module-soil

> Unified soil and geology data layer for the [Nekazari](https://github.com/nkz-os/nkz) precision agriculture platform.

[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-teal)](https://fastapi.tiangolo.com/)
[![FIWARE](https://img.shields.io/badge/FIWARE-NGSI--LD-orange)](https://www.fiware.org/)
[![Tests](https://img.shields.io/badge/tests-67%20passing-brightgreen)](tests/)

## Overview

Provides edaphological characterization for any agricultural parcel via a **multi-source provider cascade**, **pedotransfer functions**, and **FIWARE NGSI-LD** entities. When a parcel is created or updated, the module automatically ingests soil data from all available sources, merges results by priority, derives hydraulic properties, and persists an `AgriSoil` entity in the Context Broker.

## API routing (production)

| Traffic | Path | Auth |
|---------|------|------|
| Browser / modules | `https://nkz.robotika.cloud/api/soil/*` | JWT via **api-gateway** → `X-Tenant-ID`, `X-User-ID`, `X-User-Roles` |
| Orion subscription | `http://soil-module-service:8000/v1/soil/webhooks/orion` | Cluster-internal only; `NGSILD-Tenant` required |

The module frontend uses `api.basePath: '/api/soil'` (see `src/Module.tsx`). Do **not** expose a public Ingress directly to `soil-module-api` (bypasses gateway).

Internal docs: `internal-docs-local/modules/soil/` (hardening backlog). Catalog PostgreSQL: [`docs/CATALOG_INGEST.md`](docs/CATALOG_INGEST.md).

## Architecture

```
AgriParcel created in Orion-LD
        │
        ▼
  Subscription fires ──► POST /webhooks/orion
        │
        ▼
  Arq Worker (ingest_parcel)
        │
        ├──► Provider cascade (by priority)
        │     ├── Lab analysis (100) ────► highest priority
        │     ├── IoT sensors  (90)
        │     ├── IDENA WFS    (40) ─────► Navarra regional SDI
        │     ├── IGME WMS     (30) ─────► Spanish geological survey
        │     ├── BGS WMS      (30) ─────► British Geological Survey
        │     ├── LUCAS CSV    (25) ─────► EU topsoil ground truth
        │     ├── EU-HydroGrids(20) ─────► ⚠️ license-restricted
        │     └── SoilGrids    (10) ─────► ISRIC global baseline
        │
        ├──► Cache check (Redis + in-memory)
        │
        ├──► Cascade merge (high-priority wins, gaps filled)
        │
        ├──► Pedotransfer pipeline
        │     ├── Saxton-Rawls (2006) ──► Ksat, field capacity, wilting point
        │     ├── AWC calculation ──────► available water capacity
        │     ├── SCS hydrologic group ─► A/B/C/D classification
        │     └── Relative compaction ──► textural class + bulk density
        │
        └──► AgriSoil entity → Orion-LD
```

## Features

### Data Providers (8 sources)

| Provider | Priority | Coverage | Protocol | Status |
|----------|----------|----------|----------|--------|
| **Lab Analysis** | 100 | Point samples | Direct input | ✅ Functional |
| **IoT Sensors** | 90 | Real-time telemetry | MQTT → NGSI-LD | ✅ Functional |
| **IDENA** | 40 | Navarra (ES) | WFS 2.0 GeoJSON | ✅ WFS-based |
| **IGME** | 30 | Spain | WMS 1.1.1 GetFeatureInfo | ✅ Esri-compatible |
| **BGS** | 30 | United Kingdom | WMS 1.3.0 GeoJSON | ✅ Functional |
| **LUCAS** | 25 | EU-27 | CSV bulk download | ✅ Multi-URL fallback |
| **EU-SoilHydroGrids** | 20 | EU-27 | GeoTIFF (static) | ⚠️ Non-commercial license |
| **SoilGrids** | 10 | Global | REST API + WebDAV COG | ✅ Dual-mode (COG/REST) |

### Pedotransfer Functions

- **Saxton-Rawls (2006)** — Ksat, field capacity, wilting point from sand/clay/organic carbon
- **Available Water Capacity** — FC − WP differential
- **SCS Hydrologic Group** — A/B/C/D classification from Ksat
- **Relative Compaction** — textural class + bulk density classification

### Caching & Metrics

- **Two-layer cache**: Redis (shared across replicas) + in-memory fallback
- **Configurable TTL**: 1 year for stable baselines (SoilGrids), 30 days for revisable sources (IDENA, IGME, BGS)
- **Prometheus metrics**: latency (avg/p95), error rate, cache hit rate per provider
- **Circuit breaker**: Redis-backed, auto-isolates failing providers (5 failures → 15 min cooldown)

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/soil/parcel/{id}/summary` | Full AgriSoil entity for parcel |
| `GET` | `/v1/soil/parcel/{id}/horizons` | Filtered horizons by depth |
| `GET` | `/v1/soil/parcel/{id}/hydrologic-group` | SCS classification |
| `GET` | `/v1/soil/parcel/{id}/compaction-susceptibility` | Compaction risk per horizon |
| `GET` | `/v1/soil/parcel/{id}/raster` | Presigned COG URL for interpolated raster |
| `GET` | `/v1/soil/point?lat=&lon=` | Point query with spatial search |
| `GET` | `/v1/soil/point/texture?lat=&lon=&depth=` | **Canonical on-the-fly texture resolution** — for cross-module consumers |
| `POST` | `/v1/soil/sampling-points` | Create lab sampling point |
| `POST` | `/v1/soil/sampling-points/batch` | CSV batch upload |
| `POST` | `/v1/soil/parcel/{id}/ingest` | Force re-ingest parcel |
| `POST` | `/v1/soil/parcel/{id}/rasterize` | Generate intra-parcel raster from sampling points |
| `POST` | `/v1/soil/webhooks/orion` | Orion-LD subscription handler |
| `POST` | `/v1/soil/subscriptions/register` | Register AgriParcel subscription |
| `GET` | `/v1/soil/layers/manifest` | GIS layer catalog |
| `GET` | `/v1/soil/layers/parcels.geojson` | GeoJSON choropleth by soil attribute |
| `GET` | `/v1/soil/layers/{layer_id}/render` | Raster render for a layer |
| `GET` | `/v1/soil/providers/health` | Provider health status |
| `GET` | `/v1/soil/metrics` | Provider health metrics (JSON) |
| `GET` | `/v1/soil/metrics/prometheus` | Prometheus scrape format |
| `GET` | `/health` | K8s probe (rate-limit exempt) |

### NGSI-LD Entity Types

| Type | Relationship | Purpose |
|------|-------------|---------|
| `AgriSoilExtended` | `hasAgriParcel` → AgriParcel | Soil profile with horizons, pedotransfer results, compaction susceptibility, provenance |
| `SoilSamplingPoint` | `hasAgriParcel` → AgriParcel | Lab/field sampling point with analytical results |
| `SoilSurvey` | `hasAgriParcel` → AgriParcel | Survey campaign metadata |
| `SoilDerivedRaster` | `hasAgriParcel` → AgriParcel | Interpolated raster artifact reference (MinIO presigned URL) |

### Frontend Slots & Visualization

| Slot | Component | Description |
|------|-----------|-------------|
| `context-panel` | `SoilPanel` | Parcel soil summary with texture, hydrology, and penetrometer form |
| `context-panel` | `SoilProfileCard` | Vertical soil profile: stacked horizon bars coloured by USDA class, hydraulic properties table, sand/silt/clay composition, compaction susceptibility |
| `map-layer` | `SoilLayer` | Cesium GeoJSON/raster overlay coloured by selected soil attribute |
| `layer-toggle` | `SoilLayerToggle` | Map layer selector with per-attribute legend |

**Available GIS layers:** USDA texture class (12 classes, Munsell colours), hydrologic group (SCS A–D), saturated hydraulic conductivity (Ksat), clay content, organic carbon, pH, relative compaction, compaction susceptibility.

## Cross-Module Integration

This module is the **canonical soil data provider** for the Nekazari platform.
Other modules consume it via well-defined REST contracts:

| Consumer | Endpoint used | Data consumed |
|----------|--------------|---------------|
| **crop-health** | `GET /v1/soil/parcel/{id}/summary` (primary) | FC, WP, Ksat, SCS group → FAO-56 water balance, waterlogging risk |
| **crop-health** | `GET /v1/soil/parcel/{id}/compaction-susceptibility` | Compaction risk scores per horizon |
| **weather-api** | `GET /v1/soil/point/texture?lat=&lon=` | On-the-fly texture for agro-status calculations |
| **risk-worker** | `GET /v1/soil/point/texture?lat=&lon=` | Workability models |

**Configuration required on consumer side:**
```bash
SOIL_MODULE_URL=http://soil-module-service:8000
```

The module also publishes an Orion-LD subscription that auto-ingests every new
`AgriParcel`, so consumers can also query `AgriSoilExtended` entities directly
from the Context Broker (type filter + `hasAgriParcel` relationship).

## Quick Start

### Backend

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Start API server
uvicorn nkz_soil.api.main:app --reload --port 8000

# Start Arq worker
arq nkz_soil.workers.ingest.WorkerSettings
```

### Frontend (IIFE module)

```bash
cd frontend
pnpm install
pnpm dev          # Vite dev server with MockProvider
pnpm build:module # IIFE bundle → dist/nkz-module.js + dist/manifest.json
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ORION_LD_URL` | Yes | Orion-LD URL (internal: `http://orion-ld-service:1026`). Alias: `ORION_BASE_URL` |
| `ORION_WEBHOOK_SECRET` | No | Optional shared secret for `X-Orion-Webhook-Secret` on Orion notifications |
| `REDIS_URL` | Yes | Redis for cache + Arq queue (internal: `redis://redis-service:6379`) |
| `MINIO_ENDPOINT` | Yes | MinIO S3 endpoint for raster storage |
| `MINIO_ACCESS_KEY` | Yes | MinIO access key (via K8s Secret) |
| `MINIO_SECRET_KEY` | Yes | MinIO secret key (via K8s Secret) |
| `CONTEXT_URL` | Yes | NGSI-LD @context URL (internal: `http://api-gateway-service:5000/ngsi-ld-context.json`) |
| `CORS_ALLOWED_ORIGINS` | No | Comma-separated allowed origins |
| `CACHE_TTL_BASELINE` | No | Default cache TTL in seconds (default: 31536000 = 1 year) |
| `CACHE_TTL_REVISABLE` | No | Cache TTL for revisable sources (default: 2592000 = 30 days) |
| `INGESTION_BUFFER_M` | No | Geometry expansion buffer in meters (default: 50.0) |

## Deployment

### Docker

```bash
# API service
docker build -t ghcr.io/nkz-os/nkz-module-soil/api:latest -f backend/Dockerfile .

# Arq worker
docker build -t ghcr.io/nkz-os/nkz-module-soil/worker:latest -f backend/Dockerfile.worker .
```

### Kubernetes

Images are pinned by **digest** in `k8s/deployment-*.yaml` (not `:latest`). After each
GHCR push, update digests:

```bash
# amd64 manifest digest (linux)
docker manifest inspect ghcr.io/nkz-os/nkz-module-soil/soil-api:latest \
  | jq -r '.manifests[] | select(.platform.architecture=="amd64") | .digest'
```

Then set `image: ghcr.io/nkz-os/nkz-module-soil/soil-api@<digest>` and `imagePullPolicy: IfNotPresent`.

```bash
kubectl apply -f k8s/sealed-secret.yaml   # MinIO + PG credentials (SealedSecret)
kubectl apply -f k8s/configmap.yaml       # Non-secret env vars
kubectl apply -f k8s/deployment-api.yaml
kubectl apply -f k8s/deployment-worker.yaml
kubectl apply -f k8s/service.yaml
```

### Frontend (MinIO)

```bash
mc cp dist/nkz-module.js nekazari-frontend/modules/soil/
mc cp dist/manifest.json nekazari-frontend/modules/soil/
```

## Data License Boundary

This module fetches soil data from multiple third-party sources. Some sources impose
redistribution restrictions on their **raw measurements** (e.g., sand/clay/silt fractions).
The module enforces these boundaries in code:

| What | Redistributable? | Where |
|------|------------------|-------|
| Raw sand/silt/clay % from JRC LUCAS Texture (100 m) | ❌ No (JRC license) | Used internally for pedotransfer only; suppressed at entity emission |
| Raw sand/silt/clay % from ESDB, SoilGrids, lab input | ✅ Yes | Persisted in Orion-LD `AgriSoilExtended` entities |
| Derived hydraulic properties (FC, WP, Ksat, SCS group) | ✅ Always | Computed via Saxton-Rawls 2006 from the best available source; always emitted as new works |
| USDA texture class | ✅ Always | Derived classification; always emitted |
| Compaction susceptibility score | ✅ Always | Derived from texture + organic matter; always emitted |

**Bottom line for consumers (crop-health, weather-api, risk-worker):** all the
properties needed for agronomic modelling — field capacity, wilting point, Ksat,
hydrologic group, texture class — are **always available** regardless of which
provider won the cascade. Raw fractions are available when a redistributable
source (ESDB, SoilGrids, lab, or regional SDI) covered the parcel.

## Data Attribution

When displaying results in a UI, include the appropriate attribution for the
winning data source:

| Provider | Attribution |
|----------|-------------|
| IDENA | Servicio proporcionado por el Gobierno de Navarra (CC BY 4.0 ES) |
| IGME | Instituto Geológico y Minero de España |
| BGS | UKRI / British Geological Survey and Cranfield University LandIS Portal |
| SoilGrids | ISRIC World Soil Information, SoilGrids v2.0 |
| LUCAS | European Commission, JRC, LUCAS Topsoil Survey |
| EU-SoilHydroGrids | JRC ESDAC (non-commercial use only) |
| ESDB | European Soil Database, JRC ESDAC |

## Roadmap

Planned enhancements and known limitations are tracked in [ROADMAP.md](ROADMAP.md).

## License

Apache 2.0 — See [LICENSE](LICENSE)

## Powered by

- [FIWARE NGSI-LD](https://fiware-orion.readthedocs.io/)
- [ISRIC SoilGrids 2.0](https://soilgrids.org)
- [Nekazari Platform](https://github.com/nkz-os/nkz)
# trigger CI
