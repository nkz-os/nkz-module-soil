import { describe, expect, it } from 'vitest';
import {
  apiErrorDetail, buildSamplingPayload, fromSelect, labErrors, NONE, P_METHODS, K_METHODS,
} from '../samplingPayload';

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

describe('labErrors', () => {
  it('requires a method when P or K is given', () => {
    expect(labErrors({ phosphorusAvailable: '18', potassiumExchangeable: '240',
                       potassiumMethod: 'ammonium_acetate', samplingDate: '2026-09-30' }))
      .toEqual({ phosphorusMethod: 'methodRequired' });
  });
  it('requires the value when a method is chosen', () => {
    expect(labErrors({ potassiumMethod: 'ammonium_acetate' }))
      .toEqual({ potassiumExchangeable: 'valueRequired' });
  });
  it('requires the sampling date for fertility values', () => {
    expect(labErrors({ organicMatter: '2.1' })).toEqual({ samplingDate: 'dateRequired' });
  });
  it('is empty without lab fertility values', () => {
    expect(labErrors({ clay: '20' })).toEqual({});
  });
});

describe('select and API helpers', () => {
  it('maps the none option to an empty value', () => {
    expect(fromSelect(NONE)).toBe('');
    expect(fromSelect('olsen')).toBe('olsen');
  });
  it('extracts the API detail from an SDK error', () => {
    const err = new Error('HTTP 422 Unprocessable Entity: {"detail":"samplingDate must be YYYY-MM-DD"}');
    expect(apiErrorDetail(err)).toBe('samplingDate must be YYYY-MM-DD');
    const pyd = new Error('HTTP 422 : {"detail":[{"msg":"Input should be a valid number"}]}');
    expect(apiErrorDetail(pyd)).toBe('Input should be a valid number');
    expect(apiErrorDetail(new Error('network down'))).toBeNull();
  });
});

it('method lists match the backend', () => {
  expect([...P_METHODS].sort()).toEqual(['ammonium_acetate_edta', 'ammonium_lactate', 'bray1',
    'cacl2', 'calcium_lactate', 'calcium_lactate_acetate', 'mehlich3', 'olsen', 'water']);
  expect([...K_METHODS].sort()).toEqual(['ammonium_acetate', 'ammonium_lactate',
    'calcium_ammonium_lactate', 'mehlich3']);
});
