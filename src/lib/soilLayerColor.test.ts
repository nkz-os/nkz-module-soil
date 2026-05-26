import { describe, it, expect } from 'vitest';
import { soilLayerColor, LAYER_ATTRIBUTES } from './soilLayerColor';

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
