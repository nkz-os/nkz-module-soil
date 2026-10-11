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

export function methodErrors(form: Record<string, string>): Record<string, 'methodRequired'> {
  const errors: Record<string, 'methodRequired'> = {};
  if (form.phosphorusAvailable && !form.phosphorusMethod) errors.phosphorusMethod = 'methodRequired';
  if (form.potassiumExchangeable && !form.potassiumMethod) errors.potassiumMethod = 'methodRequired';
  return errors;
}
