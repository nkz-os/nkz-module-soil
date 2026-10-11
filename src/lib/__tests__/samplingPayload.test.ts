import { describe, expect, it } from 'vitest';
import { buildSamplingPayload, methodErrors, P_METHODS, K_METHODS } from '../samplingPayload';

describe('buildSamplingPayload', () => {
  it('maps form keys to API keys and drops empty fields', () => {
    expect(buildSamplingPayload({
      lat: '42.8', lon: '-1.6', depthFrom: '0', depthTo: '30',
      clay: '22', organicMatter: '2.1', phosphorusAvailable: '18', phosphorusMethod: 'olsen',
      potassiumExchangeable: '', labReference: 'LAB-1', parcelId: 'urn:ngsi-ld:AgriParcel:p1',
      samplingDate: '', operator: '',
    })).toEqual({
      lat: 42.8, lon: -1.6, depth_from: 0, depth_to: 30,
      clay: 22, organic_matter: 2.1, phosphorus_available: 18, phosphorus_method: 'olsen',
      laboratory_reference: 'LAB-1', parcel_id: 'urn:ngsi-ld:AgriParcel:p1',
    });
  });
});

describe('methodErrors', () => {
  it('requires a method when P or K is given', () => {
    expect(methodErrors({ phosphorusAvailable: '18', potassiumExchangeable: '240',
                          potassiumMethod: 'ammonium_acetate' }))
      .toEqual({ phosphorusMethod: 'methodRequired' });
  });
  it('is empty without P and K', () => {
    expect(methodErrors({ clay: '20' })).toEqual({});
  });
});

it('method lists match the backend', () => {
  expect([...P_METHODS].sort()).toEqual(['ammonium_acetate_edta', 'ammonium_lactate', 'bray1',
    'cacl2', 'calcium_lactate', 'calcium_lactate_acetate', 'mehlich3', 'olsen', 'water']);
  expect([...K_METHODS].sort()).toEqual(['ammonium_acetate', 'ammonium_lactate',
    'calcium_ammonium_lactate', 'mehlich3']);
});
