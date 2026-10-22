import { describe, it, expect } from 'vitest';
import { soilLayerColor, LAYER_ATTRIBUTES, legendFor } from './soilLayerColor';

describe('soilLayerColor', () => {
  it('lists only derived attributes', () => {
    const ids = LAYER_ATTRIBUTES.map(a => a.id);
    expect(ids).toContain('usdaTextureClass');
    expect(ids).toContain('availableWaterCapacity');
    expect(ids).toContain('hydrologicGroup');
    expect(ids).not.toContain('clay');
  });
  it('maps categorical class to a stable hex', () => {
    expect(soilLayerColor('usdaTextureClass', 'loam')).toMatch(/^#[0-9a-fA-F]{6}$/);
    expect(soilLayerColor('usdaTextureClass', 'loam'))
      .toBe(soilLayerColor('usdaTextureClass', 'loam'));
  });
  it('ramps continuous AWC into hex and clamps', () => {
    expect(soilLayerColor('availableWaterCapacity', 0)).toMatch(/^#[0-9a-fA-F]{6}$/);
    expect(soilLayerColor('availableWaterCapacity', 999)).toMatch(/^#[0-9a-fA-F]{6}$/);
  });
  it('returns a neutral grey for null', () => {
    expect(soilLayerColor('availableWaterCapacity', null)).toBe('#cccccc');
  });
});

describe('legendFor', () => {
  it('returns categorical entries with colors for usdaTextureClass', () => {
    const lg = legendFor('usdaTextureClass');
    expect(lg.kind).toBe('categorical');
    if (lg.kind === 'categorical') {
      expect(lg.entries.length).toBe(12);
      expect(lg.entries.find(e => e.value === 'loam')?.color).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
  });
  it('returns A–D groups for hydrologicGroup', () => {
    const lg = legendFor('hydrologicGroup');
    expect(lg.kind).toBe('categorical');
    if (lg.kind === 'categorical') {
      expect(lg.entries.map(e => e.value)).toEqual(['A', 'B', 'C', 'D']);
    }
  });
  it('returns a continuous ramp + range for AWC', () => {
    const lg = legendFor('availableWaterCapacity');
    expect(lg.kind).toBe('continuous');
    if (lg.kind === 'continuous') {
      expect(lg.colors.length).toBeGreaterThan(1);
      expect(lg.range).toEqual([0.05, 0.25]);
      expect(lg.unit).toBe('m³/m³');
    }
  });
});
