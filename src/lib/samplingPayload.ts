/** Sampling-point form → POST /sampling-points body (snake_case, empty fields dropped). */

export const P_METHODS = ['olsen', 'bray1', 'mehlich3', 'ammonium_lactate',
  'ammonium_acetate_edta', 'calcium_lactate', 'calcium_lactate_acetate', 'water', 'cacl2'] as const;
export const K_METHODS = ['ammonium_acetate', 'mehlich3', 'ammonium_lactate',
  'calcium_ammonium_lactate'] as const;

const NUMERIC_FIELDS: ReadonlyArray<[string, string]> = [
  ['sand', 'sand'], ['silt', 'silt'], ['clay', 'clay'],
  ['organicCarbon', 'organic_carbon'], ['organicMatter', 'organic_matter'], ['ph', 'ph'],
  ['bulkDensity', 'bulk_density'], ['penetrationResistance', 'penetration_resistance'],
  ['totalNitrogen', 'total_nitrogen'], ['nitrateN', 'nitrate_n'], ['ammoniumN', 'ammonium_n'],
  ['phosphorusAvailable', 'phosphorus_available'],
  ['potassiumExchangeable', 'potassium_exchangeable'],
  ['carbonates', 'carbonates'], ['activeLime', 'active_lime'],
];
const TEXT_FIELDS: ReadonlyArray<[string, string]> = [
  ['phosphorusMethod', 'phosphorus_method'], ['potassiumMethod', 'potassium_method'],
  ['parcelId', 'parcel_id'], ['labReference', 'laboratory_reference'],
  ['samplingDate', 'sampling_date'], ['operator', 'operator'],
];

export function buildSamplingPayload(form: Record<string, string>): Record<string, unknown> {
  const out: Record<string, unknown> = {
    lat: parseFloat(form.lat),
    lon: parseFloat(form.lon),
    depth_from: parseInt(form.depthFrom, 10),
    depth_to: parseInt(form.depthTo, 10),
  };
  for (const [key, api] of NUMERIC_FIELDS) {
    if (form[key]) out[api] = parseFloat(form[key]);
  }
  for (const [key, api] of TEXT_FIELDS) {
    if (form[key]) out[api] = form[key];
  }
  return out;
}

/** Value of the "none" option of the optional selects (Radix reserves the empty string). */
export const NONE = '__none__';

export function fromSelect(value: string): string {
  return value === NONE ? '' : value;
}

type LabErrorCode = 'methodRequired' | 'valueRequired' | 'dateRequired';

const FERTILITY_KEYS = ['organicMatter', 'totalNitrogen', 'nitrateN', 'ammoniumN',
  'phosphorusAvailable', 'potassiumExchangeable', 'carbonates', 'activeLime'];

/** Client-side mirror of the backend lab-analysis rules (the server stays authoritative). */
export function labErrors(form: Record<string, string>): Record<string, LabErrorCode> {
  const errors: Record<string, LabErrorCode> = {};
  if (form.phosphorusAvailable && !form.phosphorusMethod) errors.phosphorusMethod = 'methodRequired';
  if (form.phosphorusMethod && !form.phosphorusAvailable) errors.phosphorusAvailable = 'valueRequired';
  if (form.potassiumExchangeable && !form.potassiumMethod) errors.potassiumMethod = 'methodRequired';
  if (form.potassiumMethod && !form.potassiumExchangeable) errors.potassiumExchangeable = 'valueRequired';
  if (FERTILITY_KEYS.some((k) => form[k]) && !form.samplingDate) errors.samplingDate = 'dateRequired';
  return errors;
}

/** The `detail` of an API error thrown by the SDK client (`HTTP <status> <text>: <body>`). */
export function apiErrorDetail(err: unknown): string | null {
  const message = err instanceof Error ? err.message : '';
  const sep = message.indexOf(': ');
  if (!message.startsWith('HTTP ') || sep < 0) return null;
  try {
    const detail = (JSON.parse(message.slice(sep + 2)) as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => (d as { msg?: string }).msg).filter(Boolean).join('; ') || null;
    }
  } catch {
    return null;
  }
  return null;
}
