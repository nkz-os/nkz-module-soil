/** Unwrap NGSI-LD Property/Relationship `{ type, value }` or pass through scalars. */
export function ngsiValue<T = unknown>(field: unknown): T | undefined {
  if (field == null) return undefined;
  if (typeof field === 'object' && field !== null && 'value' in field) {
    return (field as { value: T }).value;
  }
  return field as T;
}

function unwrapDate(field: unknown): unknown {
  const v = ngsiValue<unknown>(field);
  return v && typeof v === 'object' && '@value' in v ? (v as { '@value': unknown })['@value'] : v;
}

function num(field: unknown): number | undefined {
  const v = ngsiValue<unknown>(field);
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined;
}

const round = (v: number) => Math.round(v * 1e9) / 1e9;

/** AgriSoilSample (one depth per entity, SDM units: m, fractions, soilPh) as a horizon in
 * the module units (cm, %, ph). Display only: the backend owns the full mapping. */
function agriSoilSampleHorizon(entity: Record<string, unknown>): Record<string, number> {
  const h: Record<string, number> = {};
  const depthFrom = num(entity.depthFrom);
  const depthTo = num(entity.depthTo);
  if (depthFrom !== undefined) h.depthFrom = round(depthFrom * 100);
  if (depthTo !== undefined) h.depthTo = round(depthTo * 100);
  for (const k of ['sand', 'silt', 'clay'] as const) {
    const v = num(entity[k]);
    if (v !== undefined) h[k] = round(v * 100);
  }
  const ph = num(entity.soilPh);
  if (ph !== undefined) h.ph = ph;
  return h;
}

function isAgriSoilSample(entity: Record<string, unknown>): boolean {
  return typeof entity.type === 'string' && /(^|[/:])AgriSoilSample$/.test(entity.type);
}

/** Sampling day (YYYY-MM-DD) of a soil sample of either type, or ''. */
export function sampleDate(entity: Record<string, unknown> | null | undefined): string {
  if (!entity) return '';
  const v = unwrapDate(entity.samplingDate) ?? unwrapDate(entity.dateSampled);
  return typeof v === 'string' ? v.substring(0, 10) : '';
}

/** Horizons list from either flat API summary or full NGSI-LD entity. */
export function soilHorizons(entity: Record<string, unknown> | null | undefined): unknown[] {
  if (!entity) return [];
  if (isAgriSoilSample(entity)) return [agriSoilSampleHorizon(entity)];
  const raw = entity.horizons;
  if (Array.isArray(raw)) return raw;
  const unwrapped = ngsiValue<unknown>(raw);
  if (Array.isArray(unwrapped)) return unwrapped;
  // Orion-LD returns a one-element array unwrapped: a single horizon arrives as an object.
  return unwrapped && typeof unwrapped === 'object' ? [unwrapped] : [];
}
