/** SoilGrids / provider nodata sentinels — mirrors backend nkz_soil.util.nodata */

const SOILGRIDS_NODATA: readonly number[] = [-9999, -3276.8, -3.40282347e38];

const NUMERIC_KEYS = new Set([
  'sand', 'silt', 'clay', 'organicCarbon', 'ph', 'cec', 'coarseFragments',
  'bulkDensity', 'nitrogen', 'fieldCapacity', 'wiltingPoint', 'ksatSaturated',
  'ksatMmH', 'penetrationResistance', 'availableWaterCapacity',
  'compactionSusceptibilityScore', 'organic_carbon', 'bulk_density',
]);

export function isSoilgridsNodata(value: unknown): boolean {
  if (value == null) return false;
  const n = Number(value);
  if (!Number.isFinite(n)) return false;
  return SOILGRIDS_NODATA.some((s) => Math.abs(n - s) < 1e-6);
}

export function cleanNodataValue<T>(value: T): T | undefined {
  if (typeof value === 'number' && isSoilgridsNodata(value)) return undefined;
  return value;
}

export function sanitizeHorizon(horizon: Record<string, unknown>): Record<string, unknown> {
  const out = { ...horizon };
  for (const key of NUMERIC_KEYS) {
    if (!(key in out)) continue;
    const cleaned = cleanNodataValue(out[key]);
    if (cleaned === undefined) delete out[key];
    else out[key] = cleaned;
  }
  const bd = out.bulkDensity;
  if (typeof bd === 'number' && (bd < 0.1 || bd > 2.65)) delete out.bulkDensity;
  const ph = out.ph;
  if (typeof ph === 'number' && (ph < 0 || ph > 14)) delete out.ph;
  const ksat = out.ksatSaturated;
  if (typeof ksat === 'number' && ksat < 0) delete out.ksatSaturated;
  return out;
}

export function sanitizeHorizons(horizons: unknown[]): Record<string, unknown>[] {
  return horizons.map((h) => sanitizeHorizon(h as Record<string, unknown>));
}

export interface CompactionEntry {
  depthFrom: number;
  depthTo: number;
  value: number;
  classification: string;
}

export function sanitizeCompaction(entries: CompactionEntry[]): CompactionEntry[] {
  return entries.filter((e) => {
    if (isSoilgridsNodata(e.value)) return false;
    if (!Number.isFinite(e.value)) return false;
    if (e.value < 0 || e.value > 100) return false;
    return true;
  });
}
