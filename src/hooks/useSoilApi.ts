import { API_ORIGIN } from '../services/apiOrigin';
import { useMemo } from 'react';
import { useAPI } from '@nekazari/module-kit';
import { parcelApiPath } from '../lib/normalizeParcelId';
import { activateSoilForParcel } from '../services/moduleActivation';

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
  // dataSource / uncertainty / relativeCompaction arrive as NGSI-LD Property
  // wrappers `{ type, value }` (reading.py wraps them; horizons is unwrapped).
  dataSource: { type: string; value: string };
  uncertainty: { type: string; value: number };
  relativeCompaction?: { type: string; value: SoilCompactionEntry[] };
}

const SOIL_API_BASE = `${API_ORIGIN}/api/soil`;

export interface LeafImportResult {
  accepted: Array<{
    row: number; id: string; plantCodes: string[]; dateSampled: string;
    action?: 'create' | 'update';
    /** Stored samples this row probably corrects (same lab code, same year, another id). */
    replaces?: string[];
  }>;
  rejected: Array<{ row: number; error: string }>;
  warnings: Array<{ code: string; column: string; row?: number }>;
  created: number;
}

/** A stored leaf sample of a parcel, as listed for review or deletion. */
export interface LeafSample {
  id: string;
  sampleCode: string | null;
  dateSampled: string | null;
  plantTissue: string | null;
  plantCodes: string[];
}

/** A zoning of the parcel (gis-routing): automatic (NDVI…) or manual treatment zones. */
export interface ZoningSummary {
  run_id: string; method: string | null; date: string | null; zone_count: number;
  labels: (string | null)[]; is_default: boolean;
}

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url, { credentials: 'include' });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

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

    getParcelsGeoJson: (attribute: string, scope: 'selected' | 'all', parcel?: string) =>
      api.get<{ type: string; features: Array<{ geometry: unknown; properties: Record<string, unknown> }> }>(
        `/layers/parcels.geojson?attribute=${encodeURIComponent(attribute)}` +
        `&scope=${scope}` + (parcel ? `&parcel=${encodeURIComponent(parcel)}` : '')
      ),

    uploadSamplingPoint: (data: Record<string, unknown>) =>
      api.post('/sampling-points', data),

    uploadCsv: (formData: FormData) =>
      api.post('/sampling-points/batch', formData),

    previewLeafCsv: (parcelId: string, formData: FormData) =>
      api.post<LeafImportResult>(
        `/plant-samples/batch?parcel_id=${encodeURIComponent(parcelId)}&dry_run=true`, formData),

    importLeafCsv: (parcelId: string, formData: FormData, replaceCorrected = false) =>
      api.post<LeafImportResult>(
        `/plant-samples/batch?parcel_id=${encodeURIComponent(parcelId)}&dry_run=false` +
        (replaceCorrected ? '&replace_corrected=true' : ''), formData),

    listLeafSamples: async (parcelId: string) =>
      (await api.get<{ samples: LeafSample[] }>(`/parcel/${parcelApiPath(parcelId)}/plant-samples`)).samples,

    deleteLeafSample: async (sampleId: string) => {
      const r = await fetch(`${SOIL_API_BASE}/plant-samples/${encodeURIComponent(sampleId)}`,
        { method: 'DELETE', credentials: 'include' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
    },

    // Zonings live in gis-routing; read them through the platform API origin.
    listZonings: (parcelId: string) =>
      getJson<{ zonings: ZoningSummary[] }>(
        `${API_ORIGIN}/api/routing/zonings/${encodeURIComponent(parcelId)}`).then((r) => r.zonings ?? []),

    exportLeafCsv: async (parcelId: string, zoningRunId?: string) => {
      const q = zoningRunId ? `?zoning_run_id=${encodeURIComponent(zoningRunId)}` : '';
      const r = await fetch(`${SOIL_API_BASE}/parcel/${parcelApiPath(parcelId)}/plant-samples/export.csv${q}`,
        { credentials: 'include' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.blob();
    },

    // Routes through entity-manager's activation gate (records real
    // quota usage) instead of calling soil's own /ingest endpoint
    // directly — that direct call bypassed tenant_parcel_modules entirely.
    forceIngest: (parcelId: string) => activateSoilForParcel(parcelId),

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
