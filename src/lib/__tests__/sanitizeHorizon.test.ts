import { describe, it, expect } from 'vitest';
import { isSoilgridsNodata, sanitizeHorizon, sanitizeCompaction } from '../sanitizeHorizon';

describe('sanitizeHorizon', () => {
  it('drops SoilGrids ph sentinel', () => {
    const out = sanitizeHorizon({ depthFrom: 0, depthTo: 5, ph: -3276.8, sand: 40 });
    expect(out.ph).toBeUndefined();
    expect(out.sand).toBe(40);
  });

  it('filters invalid compaction values', () => {
    const out = sanitizeCompaction([
      { depthFrom: 0, depthTo: 5, value: 85.8, classification: 'slight' },
      { depthFrom: 30, depthTo: 60, value: -2184.7, classification: 'normal' },
    ]);
    expect(out).toHaveLength(1);
    expect(out[0].value).toBe(85.8);
  });

  it('detects nodata sentinel', () => {
    expect(isSoilgridsNodata(-3276.8)).toBe(true);
    expect(isSoilgridsNodata(6.5)).toBe(false);
  });
});
