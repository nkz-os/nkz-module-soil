import { describe, it, expect, vi } from 'vitest';

vi.mock('@nekazari/module-kit', () => ({
  useAPI: () => {
    const mockGet = vi.fn();
    const mockPost = vi.fn();
    return {
      get: mockGet,
      post: mockPost,
    };
  },
}));

import { useSoilApi } from '../useSoilApi';

describe('useSoilApi', () => {
  it('returns an object with expected methods', () => {
    const api = useSoilApi();
    expect(api).toHaveProperty('getSummary');
    expect(api).toHaveProperty('getHorizons');
    expect(api).toHaveProperty('uploadSamplingPoint');
    expect(api).toHaveProperty('uploadCsv');
    expect(api).toHaveProperty('forceIngest');
    expect(api).toHaveProperty('getMetrics');
    expect(api).toHaveProperty('getParcelsGeoJson');
  });
});
