import { describe, expect, it } from 'vitest';
import { soilHorizons } from '../ngsiValue';

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
