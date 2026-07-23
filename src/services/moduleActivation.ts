import { NKZClient } from '@nekazari/sdk';

// Auth is handled via httpOnly cookie (NKZClient sends credentials: 'include').
const getAuthToken = (): string | null => null;

const getTenantId = (): string | null => {
  if (typeof window === 'undefined') return null;
  return (window as any).__nekazariAuthContext?.tenantId ?? null;
};

const getApiUrl = (): string => {
  if (typeof window !== 'undefined') {
    const env = (window as any).__ENV__;
    if (env?.VITE_API_URL) return String(env.VITE_API_URL).replace(/\/$/, '');
    if (env?.API_URL) return String(env.API_URL).replace(/\/$/, '');
    const origin = window.location.origin;
    if (origin.includes('nekazari.')) return origin.replace('nekazari.', 'nkz.');
    return origin;
  }
  return '';
};

let cachedClient: NKZClient | null = null;

function getClient(): NKZClient {
  if (!cachedClient) {
    cachedClient = new NKZClient({
      baseUrl: getApiUrl(),
      getToken: getAuthToken,
      getTenantId: getTenantId,
    });
  }
  return cachedClient;
}

export interface ModuleActivationResult {
  message: string;
  setup_status: 'pending' | 'ok' | 'error';
}

/** Activates the soil module for a parcel via entity-manager's per-parcel
 * activation gate (the coarse "is this module enabled here" registry) —
 * NOT a direct call to soil's own backend. Entity-manager dispatches to
 * soil's /internal/setup-parcel on our behalf and records real quota usage. */
export function activateSoilForParcel(parcelId: string): Promise<ModuleActivationResult> {
  const client = getClient();
  return client.post<ModuleActivationResult>(
    `/api/entities/parcels/${parcelId}/modules/soil/activate`,
    {}
  );
}
