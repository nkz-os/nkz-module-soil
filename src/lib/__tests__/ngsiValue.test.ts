import { describe, expect, it } from 'vitest';
import { sampleDate, soilHorizons } from '../ngsiValue';

describe('soilHorizons', () => {
  it('keeps a normalized list', () => {
    expect(soilHorizons({ horizons: { type: 'Property', value: [{ depthFrom: 0 }] } }))
      .toEqual([{ depthFrom: 0 }]);
  });
  it('wraps a single horizon that Orion returned unwrapped', () => {
    expect(soilHorizons({ horizons: { type: 'Property', value: { depthFrom: 0, ph: 7 } } }))
      .toEqual([{ depthFrom: 0, ph: 7 }]);
  });
  it('wraps a keyValues single horizon and handles missing', () => {
    expect(soilHorizons({ horizons: { depthFrom: 0 } })).toEqual([{ depthFrom: 0 }]);
    expect(soilHorizons({})).toEqual([]);
    expect(soilHorizons(null)).toEqual([]);
  });
});

describe('AgriSoilSample (SDM units) shown in the module units', () => {
  const sample = {
    id: 'urn:ngsi-ld:AgriSoilSample:t:abc', type: 'AgriSoilSample',
    dateSampled: { type: 'Property', value: { '@type': 'DateTime', '@value': '2026-09-01T12:00:00Z' } },
    depthFrom: { type: 'Property', value: 0.3 }, depthTo: { type: 'Property', value: 0.6 },
    sand: { type: 'Property', value: 0.45 }, silt: { type: 'Property', value: 0.3 },
    clay: { type: 'Property', value: 0.25 }, soilPh: { type: 'Property', value: 7.8 },
  };
  it('gives one horizon in cm and % with ph', () => {
    expect(soilHorizons(sample)).toEqual([{ depthFrom: 30, depthTo: 60, sand: 45, silt: 30, clay: 25, ph: 7.8 }]);
  });
  it('reads the sampling day of both types', () => {
    expect(sampleDate(sample)).toBe('2026-09-01');
    expect(sampleDate({ ...sample, dateSampled: { type: 'Property', value: '2026-09-02T12:00:00Z' } })).toBe('2026-09-02');
    expect(sampleDate({ samplingDate: { type: 'Property', value: '2024-10-01' } })).toBe('2024-10-01');
    expect(sampleDate({})).toBe('');
  });
});
