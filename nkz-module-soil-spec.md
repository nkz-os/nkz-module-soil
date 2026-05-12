# nkz-module-soil — Especificación técnica

**Estado:** Draft v0.2 · pendiente revisión equipo
**Tipo de módulo:** Core externo, multi-tenant
**Stack:** FIWARE / NGSI-LD / Kubernetes
**Licencia objetivo:** Apache 2.0

---

## 1. Propósito

Proporcionar a NKZ OS una capa unificada de datos de suelo y geología, accesible para cualquier módulo del platform (hidrología, agronomía, prescripción, valoración de tierras, modelos de carbono).

**Estrategia de doble nivel:**
- **Baseline público automático** para toda parcela del platform desde el momento en que se crea.
- **Refinamiento opcional por tenant** mediante muestreos de laboratorio, mapeo EM, NIR, etc.

El módulo es **proveedor de servicio interno**: no tiene UI propia salvo para carga de muestreos por tenant. Su valor está en los datos que sirve al resto de módulos.

---

## 2. Cobertura geográfica

| Prioridad | Región | Proveedores |
|---|---|---|
| Fundamental | Navarra | IDENA (regional SDI) |
| Alta | España | IGME MAGNA 50, MITECO |
| Alta | Reino Unido | BGS, UKSO, LandIS (versión libre) |
| Media | Europa | EU-SoilHydroGrids, LUCAS Topsoil, ESDB |
| Manta de seguridad | Global | SoilGrids 2.0 (ISRIC) |
| Máxima por punto | Tenant | Análisis de laboratorio, EM, NIR |

---

## 3. Arquitectura

### 3.1 Componentes

```
┌──────────────────────────────────────────────────────┐
│  nkz-module-soil                                     │
│                                                      │
│  ┌─────────────┐   ┌──────────────────────────────┐  │
│  │ REST API    │   │ Worker (async ingestion)     │  │
│  │ (FastAPI)   │   │                              │  │
│  └──────┬──────┘   └──────────────┬───────────────┘  │
│         │                         │                  │
│         └───────┬─────────────────┘                  │
│                 │                                    │
│         ┌───────▼─────────┐                          │
│         │ Provider Layer  │  ◄── Plugin pattern      │
│         └───────┬─────────┘                          │
│                 │                                    │
│         ┌───────▼─────────┐                          │
│         │ Pedotransfer    │                          │
│         └───────┬─────────┘                          │
│                 │                                    │
│   ┌─────────────┼─────────────┐                      │
│   ▼             ▼             ▼                      │
│ Orion       MinIO          Redis                     │
│ (NGSI-LD)   (rasters)      (cache/queue)             │
└──────────────────────────────────────────────────────┘
        ▲                          ▲
        │                          │
   Consumidores              Tenant uploads
   (hydro, agro, ...)        (UI fina)
```

### 3.2 Patrón provider

Toda fuente de datos es un plugin que implementa la interfaz `SoilDataProvider`:

```python
from typing import Protocol
from datetime import timedelta

class SoilDataProvider(Protocol):
    name: str
    priority: int                    # mayor = gana en cascada
    geographic_scope: GeographicScope
    update_cadence: timedelta

    async def covers(self, geometry: Geometry) -> bool: ...

    async def fetch(
        self,
        geometry: Geometry,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult: ...

    async def health(self) -> ProviderHealth: ...
```

**Cascada de resolución:** para una parcela dada se invocan todos los providers que cubren su geometría. Para cada celda raster, gana el provider de mayor `priority`. Los providers de menor prioridad rellenan huecos (gap-filling).

**Trazabilidad:** cada celda registra qué provider la pobló (`dataSource`) y la incertidumbre asociada.

### 3.3 Providers (todos en Fase 1)

| Provider | Priority | Tipo | Acceso |
|---|---|---|---|
| `LabAnalysisProvider` | 100 | Puntos lab tenant | DB interna |
| `IdenaProvider` | 40 | Raster + vector | WMS/WFS |
| `IgmeProvider` | 30 | Raster + vector | WMS/WFS |
| `BgsProvider` | 30 | Raster + vector | WMS/WFS / API |
| `LucasPointsProvider` | 25 | Puntos validación | CSV/API JRC |
| `EuSoilHydroGridsProvider` | 20 | Raster derivado | COG ESDAC |
| `SoilGridsProvider` | 10 | Raster global | COG ISRIC |

### 3.4 Resiliencia frente a fuentes externas

Con 7 providers externos en producción desde el día 1, la integración con APIs públicas (sin SLA contractual con NKZ OS) exige hardening explícito:

- **Cache local agresiva por provider** con TTL configurable (default 12 meses para baselines, 30 días para datos potencialmente revisables). Clave: `(provider, bbox_tile, property, depth)`.
- **Rate limiter por provider** (token bucket) con límites conservadores ajustados a la política de cada fuente. SoilGrids e IGME no publican SLA; conviene operar muy por debajo del umbral observable.
- **Reintentos con exponential backoff** + circuit breaker por provider. Si un provider falla 5 veces consecutivas, se aísla 15 minutos y la cascada degrada elegantemente al siguiente.
- **Ingestas en cola, no síncronas**, para que el alta masiva de parcelas (e.g. onboarding de un tenant grande) no sature ningún endpoint externo.
- **Métricas Prometheus por provider**: latencia, error rate, hits/misses de cache, tiempo desde última ingestión exitosa.

---

## 4. Modelo de datos NGSI-LD

Cuatro entidades principales, alineadas con el patrón `AgriParcel`/`AgriCrop` de Smart Data Models.

### 4.1 `AgriSoil`

Caracterización edafológica de un punto o zona, organizada por horizontes estándar.

```jsonld
{
  "id": "urn:ngsi-ld:AgriSoil:<uuid>",
  "type": "AgriSoil",
  "location": {
    "type": "GeoProperty",
    "value": { "type": "Polygon", "coordinates": [...] }
  },
  "relatedParcel": {
    "type": "Relationship",
    "object": "urn:ngsi-ld:AgriParcel:<id>"
  },
  "parcelVersionId": {
    "type": "Property", "value": "<snapshot id>"
  },
  "horizons": {
    "type": "Property",
    "value": [
      {
        "depthFrom": 0, "depthTo": 5,
        "sand": 45, "silt": 35, "clay": 20,
        "organicCarbon": 2.1,
        "bulkDensity": 1.32,
        "ph": 6.8,
        "cec": 18.5,
        "coarseFragments": 5,
        "ksatSaturated": 12.3,
        "availableWaterCapacity": 0.18,
        "hydrologicGroup": "B"
      }
      // 5-15, 15-30, 30-60, 60-100 cm
    ]
  },
  "dataSource": { "type": "Property", "value": "idena" },
  "uncertainty": { "type": "Property", "value": 0.15 },
  "lastUpdated": { "type": "Property", "value": "..." }
}
```

**Horizontes estándar:** 0–5, 5–15, 15–30, 30–60, 60–100 cm (alineados con SoilGrids).

**`dataSource` enum:** `lab_analysis | em_survey | nir | idena | igme | bgs | eu_soil_hydro | lucas | soilgrids | interpolated`

**`uncertainty`:** valor 0–1 propagado de la calidad del provider + distancia a punto de muestreo en caso de interpolación. **No negociable** — sin este campo los consumidores aguas abajo (hydro, agronómico) tratarían igual un dato real que uno extrapolado a 250m.

### 4.2 `SoilSamplingPoint`

Muestreo puntual con análisis de laboratorio.

```jsonld
{
  "id": "urn:ngsi-ld:SoilSamplingPoint:<uuid>",
  "type": "SoilSamplingPoint",
  "location": { "type": "GeoProperty", "value": { "type": "Point", ... } },
  "samplingDate": { ... },
  "laboratoryReference": { ... },
  "horizons": [ /* misma estructura que AgriSoil.horizons */ ],
  "operator": { ... },
  "relatedSurvey": { "type": "Relationship", "object": "..." }
}
```

### 4.3 `SoilSurvey`

Campaña de toma de datos (lab, EM, NIR, manual).

```jsonld
{
  "id": "urn:ngsi-ld:SoilSurvey:<uuid>",
  "type": "SoilSurvey",
  "surveyType": "lab" | "em" | "nir" | "auger",
  "relatedParcel": { ... },
  "startDate": { ... },
  "endDate": { ... },
  "instrumentation": { ... },
  "pointCount": { ... },
  "tenant": { ... }
}
```

### 4.4 `SoilDerivedRaster`

Referencia a artefactos raster pesados almacenados en MinIO (no se meten en Orion).

```jsonld
{
  "id": "urn:ngsi-ld:SoilDerivedRaster:<uuid>",
  "type": "SoilDerivedRaster",
  "relatedParcel": { ... },
  "property": "ksat" | "awc" | "hydrologic_group" | "clay" | ...,
  "depthFrom": 0, "depthTo": 30,
  "storageUri": "s3://nkz-soil/<tenant>/<parcel>/<hash>.tif",
  "format": "COG",
  "crs": "EPSG:25830",
  "resolution": 10,
  "generatedAt": { ... },
  "uncertainty": { ... }
}
```

---

## 5. Pedotransfer functions

Implementación inicial:

| Función | Fuente | Salida |
|---|---|---|
| `saxton_rawls_2006` | Saxton & Rawls (2006) | Ksat, capacidad de campo, punto de marchitez |
| `wosten_hypres` | Wösten et al. (1999) | Ksat (validada UE) |
| `scs_hydrologic_group` | NRCS | Grupo A/B/C/D |
| `awc_from_horizons` | Derivado FC - PWP | Capacidad agua disponible |

Cada función opera sobre la estructura `horizons` y produce campos derivados que se persisten en la propia entidad `AgriSoil` para evitar recálculos. Cuando entran datos nuevos (lab analysis, EM), se invalidan derivadas y se recalculan.

Las pedotransfer functions están aisladas en módulo propio (`nkz_soil.pedotransfer`) para que se puedan testar con vectores de validación de literatura y reutilizar fuera del módulo si hace falta.

---

## 6. API REST interna

API privada (Kubernetes ClusterIP), consumida por otros módulos del platform. **No expuesta a internet.**

### Endpoints de lectura

```
GET  /v1/soil/parcel/{parcelId}/summary
GET  /v1/soil/parcel/{parcelId}/horizons?depth=0-30
GET  /v1/soil/parcel/{parcelId}/raster?property=ksat&depth=0-30
GET  /v1/soil/parcel/{parcelId}/hydrologic-group
GET  /v1/soil/point?lat={x}&lon={y}&depth=0-30
GET  /v1/soil/layers/manifest
GET  /v1/soil/layers/{layerId}/render?parcelId={id}&depth={d}
GET  /v1/soil/providers/health
GET  /v1/soil/providers/coverage?bbox={...}
```

### Manifest de capas renderizables

El módulo no tiene UI propia, pero expone un manifest para que el selector de capas del platform pueda descubrir dinámicamente qué propiedades de suelo se pueden visualizar, con sus metadatos de renderizado. Esto evita acoplamiento entre el módulo y el frontend del platform: añadir una propiedad nueva (pH, CEC, lo que sea) aparece automáticamente en el selector sin tocar código de UI.

Formato de respuesta de `GET /v1/soil/layers/manifest`:

```json
{
  "layers": [
    {
      "id": "soil-hydrologic-group",
      "label": "Grupo hidrológico (SCS)",
      "category": "hydrology",
      "type": "categorical",
      "values": ["A", "B", "C", "D"],
      "colorRamp": ["#2c7bb6", "#abd9e9", "#fdae61", "#d7191c"],
      "unit": null,
      "depths": ["0-30", "30-60"]
    },
    {
      "id": "soil-ksat",
      "label": "Conductividad hidráulica (Ksat)",
      "category": "hydrology",
      "type": "continuous",
      "range": [0, 50],
      "unit": "mm/h",
      "colorRamp": "viridis",
      "depths": ["0-5", "5-15", "15-30", "30-60", "60-100"]
    },
    {
      "id": "soil-clay",
      "label": "Contenido en arcilla",
      "category": "texture",
      "type": "continuous",
      "range": [0, 100],
      "unit": "%",
      "colorRamp": "YlOrBr",
      "depths": ["0-30", "30-60", "60-100"]
    }
  ]
}
```

Las capas se sirven como **COG via presigned URL** desde MinIO, o como **WMS** servido desde el módulo — alineado con el estándar que ya use el platform para capas raster (módulo LiDAR).

### Endpoints de escritura (tenant)

```
POST /v1/soil/sampling-points         # carga manual o batch
POST /v1/soil/surveys                 # iniciar campaña
PUT  /v1/soil/surveys/{id}/upload     # subir resultados (lab, EM, NIR)
POST /v1/soil/parcel/{parcelId}/ingest # forzar reingesta
```

### Convenciones

- Autenticación: JWT con scope FIWARE (alineado con el resto del platform).
- Multi-tenancy: header `NGSILD-Tenant` propagado a Orion.
- Errores: RFC 7807 (problem+json).
- Versionado: prefijo `/v1/`.

---

## 7. Flujos

### 7.1 Ingestión automática (parcela nueva)

```
1. Evento: AgriParcel creado/actualizado
   └─> Suscripción NGSI-LD dispara worker
2. Worker calcula geometría + buffer (50-100m para análisis hidro futuro)
3. Worker consulta SoilDataProvider.covers() en todos los providers
4. Por cada provider que cubre, fetch en paralelo
5. Cascada de prioridad por celda → mosaico unificado
6. Pedotransfer → propiedades derivadas
7. Persistencia:
   - AgriSoil + horizons → Orion
   - Rasters → MinIO
   - SoilDerivedRaster (referencias) → Orion
8. Emite notificación NGSI-LD para consumidores
```

### 7.2 Consulta desde otro módulo (ej. hydro)

```
1. hydro pregunta GET /v1/soil/parcel/{id}/hydrologic-group
2. Soil consulta Orion por AgriSoil + SoilDerivedRaster asociados
3. Si existe y no stale → sirve referencia MinIO
4. Si stale o falta → trigger reingesta async + respuesta 202 Accepted
5. hydro suscribe a la notificación o reintenta
```

### 7.3 Refinamiento por tenant

```
1. Tenant sube SoilSamplingPoint vía POST
2. Validación schema + georef + sanity checks (rangos físicos)
3. Persistencia en Orion
4. Trigger reingesta de las parcelas afectadas
5. LabAnalysisProvider (priority 100) gana en su radio de influencia
6. Interpolación kriging/IDW propaga el efecto hasta distancia umbral
```

---

## 8. Almacenamiento

| Tipo de dato | Sistema | Notas |
|---|---|---|
| Entidades NGSI-LD | Orion Context Broker | Multi-tenant vía header |
| Rasters (COG) | MinIO | Bucket por tenant: `nkz-soil-{tenant}` |
| Tareas async | Redis | Cola + cache |
| Estado workers / jobs | Postgres | Solo si Redis insuficiente |
| Muestreos lab | Orion (SoilSamplingPoint) | |

**Convención de claves MinIO:**
```
nkz-soil-{tenant}/{parcelId}/{parcelVersionId}/{property}-{depth}.tif
```

---

## 9. Estructura del repositorio

```
nkz-module-soil/
├── README.md
├── LICENSE                       # Apache 2.0
├── pyproject.toml
├── docker/
│   ├── Dockerfile.api
│   └── Dockerfile.worker
├── helm/
│   └── nkz-module-soil/          # chart K8s
├── src/nkz_soil/
│   ├── api/                      # FastAPI endpoints
│   ├── workers/                  # tasks async
│   ├── providers/
│   │   ├── base.py               # Protocol + GeographicScope
│   │   ├── soilgrids.py
│   │   ├── eu_soil_hydro.py
│   │   ├── lucas.py
│   │   ├── igme.py
│   │   ├── bgs.py
│   │   ├── idena.py
│   │   └── lab_analysis.py
│   ├── pedotransfer/
│   │   ├── saxton_rawls.py
│   │   ├── wosten.py
│   │   └── scs_groups.py
│   ├── interpolation/
│   │   ├── kriging.py
│   │   └── idw.py
│   ├── models/
│   │   ├── ngsi_ld.py            # Pydantic models de entidades
│   │   └── domain.py             # Tipos internos
│   ├── storage/
│   │   ├── orion.py
│   │   └── minio.py
│   └── config/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   ├── providers.md
│   └── adding-a-provider.md
└── ngsi-ld-models/               # JSON-LD context + ejemplos
    ├── AgriSoil.jsonld
    ├── SoilSamplingPoint.jsonld
    ├── SoilSurvey.jsonld
    └── SoilDerivedRaster.jsonld
```

---

## 10. Stack técnico

- **Lenguaje:** Python 3.12+
- **API:** FastAPI + uvicorn
- **Async / queue:** Redis + Arq (o RQ; decisión equipo)
- **Geo:** GDAL, rasterio, PDAL, shapely, geopandas, pyproj
- **WMS/WFS:** OWSLib
- **Interpolación:** PyKrige, scikit-gstat
- **HTTP:** httpx
- **Validación:** Pydantic v2
- **Tests:** pytest + pytest-asyncio + respx (mocking HTTP)
- **Lint/format:** ruff + mypy
- **Deploy:** Docker + Helm chart

---

## 11. Fases de desarrollo

### Fase 1 — Lanzamiento con cobertura completa (objetivo: 10–12 semanas)

Cobertura total de providers públicos desde el día 1. El módulo arranca productivo para cualquier tenant europeo.

**Infraestructura del módulo:**
- [ ] Interfaz `SoilDataProvider` + registro de plugins
- [ ] Cache local + rate limiter + circuit breaker por provider
- [ ] Métricas Prometheus por provider
- [ ] Worker de ingestión disparado por evento `AgriParcel`
- [ ] Helm chart funcional en dev y staging

**Providers (todos):**
- [ ] `SoilGridsProvider` (manta de seguridad global)
- [ ] `EuSoilHydroGridsProvider` (Europa, derivados hidráulicos)
- [ ] `LucasPointsProvider` (puntos de validación EU+UK histórico)
- [ ] `IgmeProvider` (España)
- [ ] `BgsProvider` (UK, versión libre 1:250.000)
- [ ] `IdenaProvider` (Navarra — showcase)
- [ ] `LabAnalysisProvider` (carga puntual de análisis por tenant, sin UI compleja)

**Pedotransfer:**
- [ ] Saxton-Rawls (2006)
- [ ] Wösten / HYPRES
- [ ] Grupo hidrológico SCS
- [ ] AWC desde horizontes
- [ ] Propagación de incertidumbre

**Modelo y API:**
- [ ] Entidades NGSI-LD: `AgriSoil`, `SoilSamplingPoint`, `SoilSurvey`, `SoilDerivedRaster`
- [ ] Endpoints de lectura (incluido manifest de capas)
- [ ] Endpoints de carga de muestreos (POST sampling-points / surveys)
- [ ] Servicio de capas renderizables (COG / WMS)

**Calidad:**
- [ ] Tests unitarios por provider con HTTP mockeado
- [ ] Integración nocturna contra endpoints reales
- [ ] Validación cruzada inicial contra LUCAS

**Definition of done Fase 1:** crear una `AgriParcel` en cualquier país europeo (con foco verificado en Navarra, España, UK) produce automáticamente una `AgriSoil` consultable, con grupo hidrológico, Ksat y propiedades derivadas, en menos de 5 minutos. El selector de capas del platform descubre dinámicamente las propiedades renderizables vía manifest.

### Fase 2 — Refinamiento avanzado (4–6 semanas)

- [ ] UI completa de carga de muestreos (batch CSV, validación visual)
- [ ] Interpolación kriging/IDW para propagar puntos de muestreo
- [ ] Reingesta selectiva en zona de influencia
- [ ] Workflow de aprobación de muestreos (revisión antes de publicar)

### Fase 3 — Sensores avanzados

- [ ] Ingesta EM (Veris, EM38) con calibración
- [ ] Ingesta NIR proximal
- [ ] Validación cruzada continua contra LUCAS
- [ ] Integración licenciada de BGS LandIS NATMAP alta resolución (opcional por tenant)

---

## 12. Testing & validación

- **Unitarios:** una batería por provider con HTTP mockeado (respx). Pedotransfer functions con vectores de validación de literatura.
- **Integración:** sandbox contra endpoints reales de SoilGrids, IDENA, IGME en CI nocturno.
- **Validación científica:** comparación de propiedades derivadas contra puntos LUCAS donde haya solape geográfico. Métrica: RMSE por propiedad.
- **Performance:** benchmark de tiempo de ingestión por km² por provider.
- **Carga:** simular ingestión simultánea de N parcelas (objetivo a definir con producto).

---

## 13. Decisiones pendientes para el equipo

Antes del kickoff:

1. **Cola de tareas:** Arq vs RQ vs Celery. Sugerencia: Arq (asyncio-native, ligero).
2. **Política de invalidación de cache:** ¿cada cuánto se re-consulta SoilGrids para una parcela existente? Sugerencia: 12 meses, configurable por tenant.
3. **Serving de rasters:** ¿COG streaming directo desde MinIO con presigned URLs, o capa de tiles intermedia? Sugerencia: COG streaming para Fase 1, tiles si performance lo exige.
4. **Autenticación API interna:** mTLS (mesh) vs JWT. Alinear con el resto de módulos del platform.
5. **CI/CD:** confirmar si existe template NKZ OS a heredar.
6. **Repo:** ubicación, permisos, branch policy.
7. **Estrategia BGS UK:** confirmar si Fase 1 arranca solo con LandIS libre (1:250.000) y SoilGrids como detalle, o si se evalúa ya licencia comercial Cranfield.

---

## 14. Riesgos identificados

| Riesgo | Mitigación |
|---|---|
| WMS/WFS de IDENA o IGME caídos durante ingesta | Cascada de fallback + cache local con TTL largo + circuit breaker |
| Rate limit / bloqueo de APIs públicas (SoilGrids, IGME) en altas masivas | Rate limiter por provider, cola de ingestión, backoff exponencial, monitorización |
| Volumen de rasters en MinIO escala mal | Compresión COG, política de retención por tenant, tiling jerárquico |
| Pedotransfer functions imprecisas fuera de rango calibración | Validación contra LUCAS, alertar en `uncertainty` |
| LUCAS UK no se actualiza post-Brexit | Aceptar puntos históricos como anclaje; complementar con BGS |
| Heterogeneidad formato LUCAS entre rondas (2009-2022) | Normalización en `LucasPointsProvider`, schema unificado interno |
| BGS LandIS libre solo a 1:250.000 — resolución insuficiente para uso agronómico fino en UK | SoilGrids rellena detalle; flag para upgrade a licencia comercial por tenant en Fase 3 |
| Cambio de geometría de parcela (resize) | `parcelVersionId` en todas las entidades; ingesta nueva no destructiva |

---

## 15. Integración con módulos consumidores

### nkz-module-hydro (próximo)

Consumirá vía API interna:
- `GET /v1/soil/parcel/{id}/hydrologic-group` → SCS curve number
- `GET /v1/soil/parcel/{id}/raster?property=ksat` → infiltración
- `GET /v1/soil/parcel/{id}/raster?property=awc` → balance hídrico

Sin acoplamiento: hydro no conoce providers, solo el contrato REST.

### weather-worker (ya en core)

No hay acoplamiento directo, pero hydro combinará outputs de ambos. Conviene alinear convenciones de `parcelVersionId` y trazabilidad de fuente.

---

## Anexo A — Referencias

- ISRIC SoilGrids 2.0 — https://soilgrids.org
- JRC ESDAC — https://esdac.jrc.ec.europa.eu
- IGME MAGNA 50 — https://info.igme.es
- IDENA Navarra — https://idena.navarra.es
- British Geological Survey — https://www.bgs.ac.uk
- Saxton & Rawls (2006), Soil Science Society of America Journal 70(5)
- Wösten et al. (1999), HYPRES database
- FIWARE Smart Data Models — https://smartdatamodels.org

---

*Fin del documento.*
