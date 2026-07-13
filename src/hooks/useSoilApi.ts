import { useMemo } from 'react';
import { useAPI } from '@nekazari/module-kit';
import { parcelApiPath } from '../lib/normalizeParcelId';

export interface SoilSummary {
  horizons: Array<{
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
    hydrologicGroup?: string;
    penetrationResistance?: number;
  }>;
  dataSource: string;
  uncertainty: number;
  relativeCompaction?: Array<{
    depthFrom: number;
    depthTo: number;
    value: number;
    classification: string;
  }>;
}

const SOIL_API_BASE = '/api/soil';

export function useSoilApi() {
  const api = useAPI(SOIL_API_BASE);

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
