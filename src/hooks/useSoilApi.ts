import { useMemo } from 'react';
import { useAPI } from '@nekazari/module-kit';
import { parcelApiPath } from '../lib/normalizeParcelId';

// Flat horizon shape as returned by GET /parcel/{id}/summary (already
// unwrapped from NGSI-LD Property `{ type, value }` wrappers server-side —
// see backend/src/nkz_soil/api/routes/reading.py::parcel_summary). Fields
// mirror what the ingest worker writes per horizon
// (backend/src/nkz_soil/workers/ingest.py).
export interface SoilHorizon {
  depthFrom: number;
  depthTo: number;
  sand?: number;
  silt?: number;
  clay?: number;
  organicCarbon?: number;
  bulkDensity?: number;
  ph?: number;
  ksatSaturated?: number;
  availableWaterCapacity?: number;
  fieldCapacity?: number;
  wiltingPoint?: number;
  hydrologicGroup?: string;
  usdaTextureClass?: string;
  penetrationResistance?: number;
}

export interface SoilCompactionEntry {
  depthFrom: number;
  depthTo: number;
  value: number;
  classification: string;
}

export interface SoilSummary {
  horizons: SoilHorizon[];
  dataSource: string;
  uncertainty: number;
  relativeCompaction?: SoilCompactionEntry[];
}

const SOIL_API_BASE = '/api/soil';

type ApiClient = { get: <T = unknown>(path: string) => Promise<T>; post: <T = unknown>(path: string, body?: unknown) => Promise<T> };

/** Pure builder — kept separate from the hook so it is unit-testable without a React render. */
export function buildSoilApi(api: ApiClient) {
  return {
    get: api.get.bind(api),
    post: api.post.bind(api),

    getSummary: (parcelId: string) =>
      api.get<SoilSummary>(`/parcel/${parcelApiPath(parcelId)}/summary`),

    getHorizons: (parcelId: string, depth = '0-30') =>
      api.get<{ horizons: SoilSummary['horizons'] }>(
        `/parcel/${parcelApiPath(parcelId)}/horizons?depth=${encodeURIComponent(depth)}`
      ),

    getWaterBudget: (parcelId: string) =>
      api.get<Record<string, unknown>>(`/parcel/${parcelApiPath(parcelId)}/water-budget`),

    getParcelsGeoJson: (attribute: string, scope: 'selected' | 'all', parcel?: string) =>
      api.get<{ type: string; features: Array<{ geometry: unknown; properties: Record<string, unknown> }> }>(
        `/layers/parcels.geojson?attribute=${encodeURIComponent(attribute)}` +
        `&scope=${scope}` + (parcel ? `&parcel=${encodeURIComponent(parcel)}` : '')
      ),

    uploadSamplingPoint: (data: Record<string, unknown>) =>
      api.post('/sampling-points', data),

    uploadCsv: (formData: FormData) =>
      api.post('/sampling-points/batch', formData),

    forceIngest: (parcelId: string) =>
      api.post(`/parcel/${parcelApiPath(parcelId)}/ingest`, {}),

    getMetrics: () =>
      api.get<{ providers: Array<{
        provider: string;
        latency: { min: number; max: number; avg: number; p95: number; count: number };
        error_rate: number;
        cache: { hits: number; misses: number; hit_rate: number };
        total_fetches: number;
        total_errors: number;
      }> }>('/metrics'),
  };
}

export function useSoilApi() {
  const api = useAPI(SOIL_API_BASE);

  // Memoize on the (stable) api client: consumers put this object in useEffect
  // dependency arrays (ModulePage summary fetch), so a fresh object each render
  // would loop renders/fetches forever.
  return useMemo(() => buildSoilApi(api), [api]);
}
