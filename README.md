# nkz-module-soil

Unified soil and geology data layer for the Nekazari platform.

Provides edaphological characterization for any parcel via a multi-source provider cascade, pedotransfer functions, and NGSI-LD entities.

## Architecture

- **8 data providers** with priority-based cascade: lab analysis (100) → IoT sensors (90) → regional SDI (30-40) → validation points (25) → EU/global baselines (10-20)
- **5 pedotransfer functions**: Saxton-Rawls (2006), Wosten/HYPRES, SCS hydrologic group, AWC, relative compaction
- **4 NGSI-LD entity types**: `AgriSoil`, `SoilSamplingPoint`, `SoilSurvey`, `SoilDerivedRaster`
- **Async ingestion** via Arq worker, triggered by `AgriParcel` subscriptions
- **COG raster serving** via MinIO with presigned URLs

## API

Internal REST API (routes through api-gateway). See `backend/src/nkz_soil/api/routes/` for full endpoint reference.

## Development

```bash
# Backend
pip install -e ".[dev]"
pytest tests/ -v

# Frontend
cd frontend && npm install && npm run build:module
```

## Deployment

K8s manifests in `k8s/`. See `manifest.json` for module metadata.

## License

Apache 2.0 — See [LICENSE](LICENSE)

## Powered by

- [FIWARE NGSI-LD](https://fiware-orion.readthedocs.io/)
- [ISRIC SoilGrids 2.0](https://soilgrids.org)
- [NKZ Platform SDK](https://github.com/nkz-os/nkz)
