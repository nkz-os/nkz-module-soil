import { describe, it, expect, vi } from 'vitest';
import { buildSoilApi } from '../useSoilApi';

vi.mock('../../services/moduleActivation', () => ({
  activateSoilForParcel: vi.fn().mockResolvedValue({ message: 'ok', setup_status: 'ok' }),
}));

import { activateSoilForParcel } from '../../services/moduleActivation';

function mockClient() {
  return { get: vi.fn(), post: vi.fn() };
}

describe('buildSoilApi', () => {
  it('returns an object with expected methods', () => {
    const api = buildSoilApi(mockClient());
    expect(api).toHaveProperty('getSummary');
    expect(api).toHaveProperty('getHorizons');
    expect(api).toHaveProperty('uploadSamplingPoint');
    expect(api).toHaveProperty('uploadCsv');
    expect(api).toHaveProperty('forceIngest');
    expect(api).toHaveProperty('getMetrics');
    expect(api).toHaveProperty('getParcelsGeoJson');
  });

  it('binds calls to the provided client', () => {
    // useSoilApi wraps this in useMemo([api]); since useAPI returns a client
    // memoized on basePath, the wrapped object is referentially stable across
    // renders — preventing the ModulePage summary-fetch effect (dep [.., api])
    // from looping forever.
    const client = mockClient();
    buildSoilApi(client).getSummary('urn:ngsi-ld:AgriParcel:x');
    expect(client.get).toHaveBeenCalledTimes(1);
    expect(String(client.get.mock.calls[0][0])).toContain('/summary');
  });

  it('forceIngest routes through the module activation gate, not a direct /ingest call', async () => {
    const client = mockClient();
    await buildSoilApi(client).forceIngest('urn:ngsi-ld:AgriParcel:abc');
    expect(activateSoilForParcel).toHaveBeenCalledWith('urn:ngsi-ld:AgriParcel:abc');
    expect(client.post).not.toHaveBeenCalled();
  });
});
