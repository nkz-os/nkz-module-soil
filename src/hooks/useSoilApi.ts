import { useAPI } from '@nekazari/module-kit';

interface SoilSummary {
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

export function useSoilApi() {
  const api = useAPI();

  return {
    getSummary: (parcelId: string) =>
      api.get<SoilSummary>(`/v1/soil/parcel/${parcelId}/summary`),

    getHorizons: (parcelId: string, depth = '0-30') =>
      api.get<{ horizons: SoilSummary['horizons'] }>(
        `/v1/soil/parcel/${parcelId}/horizons?depth=${depth}`
      ),

    getParcelsGeoJson: (attribute: string, scope: 'selected' | 'all', parcel?: string) =>
      api.get<{ type: string; features: Array<{ geometry: unknown; properties: Record<string, unknown> }> }>(
        `/v1/soil/layers/parcels.geojson?attribute=${encodeURIComponent(attribute)}` +
        `&scope=${scope}` + (parcel ? `&parcel=${encodeURIComponent(parcel)}` : '')
      ),

    uploadSamplingPoint: (data: Record<string, unknown>) =>
      api.post('/v1/soil/sampling-points', data),

    uploadCsv: (formData: FormData) =>
      api.post('/v1/soil/sampling-points/batch', formData),

    forceIngest: (parcelId: string) =>
      api.post(`/v1/soil/parcel/${parcelId}/ingest`, {}),

    getMetrics: () =>
      api.get<{ providers: Array<{
        provider: string;
        latency: { min: number; max: number; avg: number; p95: number; count: number };
        error_rate: number;
        cache: { hits: number; misses: number; hit_rate: number };
        total_fetches: number;
        total_errors: number;
      }> }>('/v1/soil/metrics'),
  };
}
