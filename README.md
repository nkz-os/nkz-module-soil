# nkz-module-soil

> Unified soil and geology data layer for the [Nekazari](https://github.com/nkz-os/nkz) precision agriculture platform.

[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-teal)](https://fastapi.tiangolo.com/)
[![FIWARE](https://img.shields.io/badge/FIWARE-NGSI--LD-orange)](https://www.fiware.org/)
[![Tests](https://img.shields.io/badge/tests-67%20passing-brightgreen)](tests/)

## Overview

Provides edaphological characterization for any agricultural parcel via a **multi-source provider cascade**, **pedotransfer functions**, and **FIWARE NGSI-LD** entities. When a parcel is created or updated, the module automatically ingests soil data from all available sources, merges results by priority, derives hydraulic properties, and persists an `AgriSoil` entity in the Context Broker.

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
| `GET` | `/v1/soil/point?lat=&lon=` | Point query with spatial search |
| `POST` | `/v1/soil/sampling-points` | Create lab sampling point |
| `POST` | `/v1/soil/parcel/{id}/ingest` | Force re-ingest parcel |
| `POST` | `/v1/soil/webhooks/orion` | Orion-LD subscription handler |
| `POST` | `/v1/soil/subscriptions/register` | Register AgriParcel subscription |
| `GET` | `/v1/soil/metrics` | Provider health metrics (JSON) |
| `GET` | `/v1/soil/metrics/prometheus` | Prometheus scrape format |
| `GET` | `/health` | K8s probe (rate-limit exempt) |

### NGSI-LD Entity Types

| Type | Purpose |
|------|---------|
| `AgriSoil` | Soil profile with horizons, pedotransfer results, uncertainty |
| `SoilSamplingPoint` | Lab/field sampling point with analytical results |
| `SoilSurvey` | Survey campaign metadata |
| `SoilDerivedRaster` | Raster artifact reference (MinIO presigned URL) |

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
| `ORION_BASE_URL` | Yes | Orion-LD Context Broker URL (internal: `http://orion-ld-service:1026`) |
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

```bash
kubectl apply -f k8s/secret.yaml      # MinIO credentials (edit first)
kubectl apply -f k8s/configmap.yaml   # Non-secret env vars
kubectl apply -f k8s/deployment-api.yaml
kubectl apply -f k8s/deployment-worker.yaml
kubectl apply -f k8s/service.yaml
```

### Frontend (MinIO)

```bash
mc cp dist/nkz-module.js nekazari-frontend/modules/soil/
mc cp dist/manifest.json nekazari-frontend/modules/soil/
```

## Data Attribution

This module integrates data from multiple sources. When displaying results, include the appropriate attribution:

| Provider | Attribution |
|----------|-------------|
| IDENA | Servicio proporcionado por el Gobierno de Navarra (CC BY 4.0 ES) |
| IGME | Instituto Geológico y Minero de España |
| BGS | UKRI / British Geological Survey and Cranfield University LandIS Portal |
| SoilGrids | ISRIC World Soil Information, SoilGrids v2.0 |
| LUCAS | European Commission, JRC, LUCAS Topsoil Survey |
| EU-SoilHydroGrids | JRC ESDAC (non-commercial use only) |

## License

Apache 2.0 — See [LICENSE](LICENSE)

## Powered by

- [FIWARE NGSI-LD](https://fiware-orion.readthedocs.io/)
- [ISRIC SoilGrids 2.0](https://soilgrids.org)
- [Nekazari Platform](https://github.com/nkz-os/nkz)
