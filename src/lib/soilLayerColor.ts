export interface LayerAttribute {
  id: string;
  kind: 'categorical' | 'continuous';
  unit?: string;
  range?: [number, number];
}

export const LAYER_ATTRIBUTES: LayerAttribute[] = [
  { id: 'usdaTextureClass', kind: 'categorical' },
  { id: 'hydrologicGroup', kind: 'categorical' },
  { id: 'availableWaterCapacity', kind: 'continuous', unit: 'm³/m³', range: [0.05, 0.25] },
  { id: 'ksatSaturated', kind: 'continuous', unit: 'mm/h', range: [0, 60] },
  { id: 'compactionSusceptibilityScore', kind: 'continuous', unit: 'score', range: [0, 100] },
];

const CATEGORICAL: Record<string, string> = {
  'sand': '#e9d8a6', 'loamy-sand': '#e6c878', 'sandy-loam': '#d8a657',
  'loam': '#bb9457', 'silt-loam': '#a3b18a', 'silt': '#8cb369',
  'sandy-clay-loam': '#c98b5b', 'clay-loam': '#9c6644', 'silty-clay-loam': '#7f9172',
  'sandy-clay': '#9e2a2b', 'silty-clay': '#6d597a', 'clay': '#582f0e',
  'A': '#2d6a4f', 'B': '#52b788', 'C': '#f4a261', 'D': '#bc4749',
};

const NEUTRAL = '#cccccc';
const RAMP = ['#2c7bb6', '#abd9e9', '#ffffbf', '#fdae61', '#d7191c'];

// Compaction susceptibility: green→yellow→orange→red (low→very_high risk)
const COMPACTION_RAMP = ['#27ae60', '#2ecc71', '#f39c12', '#e67e22', '#c0392b'];

const COMPACTION_SCORE = [0, 25, 55, 70, 100];

function lerpHex(a: string, b: string, t: number): string {
  const pa = [1, 3, 5].map(i => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map(i => parseInt(b.slice(i, i + 2), 16));
  const p = pa.map((v, i) => Math.round(v + (pb[i] - v) * t));
  return '#' + p.map(v => v.toString(16).padStart(2, '0')).join('');
}

export function soilLayerColor(attribute: string, value: string | number | null): string {
  if (value === null || value === undefined) return NEUTRAL;
  const attr = LAYER_ATTRIBUTES.find(a => a.id === attribute);
  if (attr?.kind === 'categorical' || typeof value === 'string') {
    return CATEGORICAL[String(value)] ?? NEUTRAL;
  }

  // Use compaction-specific color ramp for the susceptibility attribute
  if (attribute === 'compactionSusceptibilityScore') {
    const score = Number(value);
    for (let i = COMPACTION_SCORE.length - 1; i >= 0; i--) {
      if (score >= COMPACTION_SCORE[i]) {
        if (i >= COMPACTION_SCORE.length - 1) return COMPACTION_RAMP[COMPACTION_RAMP.length - 1];
        const segT = (score - COMPACTION_SCORE[i]) / (COMPACTION_SCORE[i + 1] - COMPACTION_SCORE[i]);
        return lerpHex(COMPACTION_RAMP[i], COMPACTION_RAMP[i + 1], segT);
      }
    }
    return COMPACTION_RAMP[0];
  }

  // Penetrometer resistance (MPa): green (<1) → yellow (1-2) → orange (2-3) → red (>3)
  if (attribute === 'penetrationResistance') {
    const mpa = Number(value);
    if (mpa < 1.0) return '#27ae60';
    if (mpa < 2.0) return '#f39c12';
    if (mpa < 3.0) return '#e67e22';
    return '#c0392b';
  }

  const [min, max] = attr?.range ?? [0, 1];
  const t = Math.max(0, Math.min(1, (Number(value) - min) / (max - min || 1)));
  const seg = t * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(seg));
  return lerpHex(RAMP[i], RAMP[i + 1], seg - i);
}

// USDA texture classes (kebab slugs from backend usda_texture.py) + hydrologic groups,
// kept here so the legend can enumerate them without re-deriving colors.
export const USDA_TEXTURE_CLASSES = [
  'sand', 'loamy-sand', 'sandy-loam', 'loam', 'silt-loam', 'silt',
  'sandy-clay-loam', 'clay-loam', 'silty-clay-loam', 'sandy-clay', 'silty-clay', 'clay',
];
export const HYDROLOGIC_GROUPS = ['A', 'B', 'C', 'D'];

export type Legend =
  | { kind: 'categorical'; entries: { value: string; color: string }[] }
  | { kind: 'continuous'; colors: string[]; range: [number, number]; unit?: string };

/** Legend descriptor for an attribute — reuses soilLayerColor/RAMP so map and legend never drift. */
export function legendFor(attribute: string): Legend {
  const attr = LAYER_ATTRIBUTES.find(a => a.id === attribute);
  if (attr?.kind === 'continuous') {
    const colors = attribute === 'compactionSusceptibilityScore' ? COMPACTION_RAMP : RAMP;
    return { kind: 'continuous', colors, range: attr.range ?? [0, 1], unit: attr.unit };
  }
  const values = attribute === 'hydrologicGroup' ? HYDROLOGIC_GROUPS : USDA_TEXTURE_CLASSES;
  return { kind: 'categorical', entries: values.map(v => ({ value: v, color: soilLayerColor(attribute, v) })) };
}
