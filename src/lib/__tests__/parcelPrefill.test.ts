import { describe, it, expect } from 'vitest';
import {
  matchParcelId,
  parcelCentroidLatLon,
  applyParcelPrefill,
} from '../parcelPrefill';

describe('matchParcelId', () => {
  const parcels = [
    { id: 'urn:ngsi-ld:AgriParcel:acme-field-01' },
    { id: 'urn:ngsi-ld:AgriParcel:demo-parcel' },
    { id: 'short-parcel-id' },
  ];

  it('returns null on empty or missing inputs', () => {
    expect(matchParcelId(null, parcels)).toBeNull();
    expect(matchParcelId(undefined, parcels)).toBeNull();
    expect(matchParcelId('', parcels)).toBeNull();
    expect(matchParcelId('   ', parcels)).toBeNull();
    expect(matchParcelId('demo-parcel', null)).toBeNull();
    expect(matchParcelId('demo-parcel', undefined)).toBeNull();
    expect(matchParcelId('demo-parcel', [])).toBeNull();
  });

  it('matches full URN directly', () => {
    expect(matchParcelId('urn:ngsi-ld:AgriParcel:acme-field-01', parcels)).toBe(
      'urn:ngsi-ld:AgriParcel:acme-field-01',
    );
  });

  it('matches short ID against full URN parcel', () => {
    expect(matchParcelId('demo-parcel', parcels)).toBe(
      'urn:ngsi-ld:AgriParcel:demo-parcel',
    );
  });

  it('matches full URN against short ID parcel', () => {
    expect(matchParcelId('urn:ngsi-ld:AgriParcel:short-parcel-id', parcels)).toBe(
      'short-parcel-id',
    );
  });

  it('trims whitespace around requested query', () => {
    expect(matchParcelId('  demo-parcel  ', parcels)).toBe(
      'urn:ngsi-ld:AgriParcel:demo-parcel',
    );
  });

  it('returns null when no parcel matches', () => {
    expect(matchParcelId('non-existent-parcel', parcels)).toBeNull();
  });
});

describe('parcelCentroidLatLon', () => {
  it('returns null for null, undefined, or missing location', () => {
    expect(parcelCentroidLatLon(null)).toBeNull();
    expect(parcelCentroidLatLon(undefined)).toBeNull();
    expect(parcelCentroidLatLon({})).toBeNull();
    expect(parcelCentroidLatLon({ location: null })).toBeNull();
  });

  it('extracts centroid from Point geometry (flat and NGSI-LD Property wrapped)', () => {
    const flatPoint = {
      location: {
        type: 'Point',
        coordinates: [-1.5, 43.25],
      },
    };
    expect(parcelCentroidLatLon(flatPoint)).toEqual({
      lat: '43.250000',
      lon: '-1.500000',
    });

    const ngsiWrapped = {
      location: {
        type: 'Property',
        value: {
          type: 'Point',
          coordinates: [2.1234567, 48.9876543],
        },
      },
    };
    expect(parcelCentroidLatLon(ngsiWrapped)).toEqual({
      lat: '48.987654',
      lon: '2.123457',
    });
  });

  it('extracts centroid from Polygon outer ring, excluding closing duplicate vertex', () => {
    // 10x10 square: corners (0,0), (10,0), (10,10), (0,10) with closing (0,0)
    const polygon = {
      location: {
        type: 'Polygon',
        coordinates: [
          [
            [0, 0],
            [10, 0],
            [10, 10],
            [0, 10],
            [0, 0], // closing duplicate should be excluded from average
          ],
        ],
      },
    };
    // Expected average: lon = (0 + 10 + 10 + 0) / 4 = 5.0, lat = (0 + 0 + 10 + 10) / 4 = 5.0
    expect(parcelCentroidLatLon(polygon)).toEqual({
      lat: '5.000000',
      lon: '5.000000',
    });
  });

  it('extracts centroid from MultiPolygon outer ring', () => {
    const multiPolygon = {
      location: {
        type: 'MultiPolygon',
        coordinates: [
          [
            [
              [-2.0, 42.0],
              [-1.0, 42.0],
              [-1.0, 43.0],
              [-2.0, 43.0],
              [-2.0, 42.0],
            ],
          ],
        ],
      },
    };
    expect(parcelCentroidLatLon(multiPolygon)).toEqual({
      lat: '42.500000',
      lon: '-1.500000',
    });
  });

  it('returns null if coordinates are out of bounds or invalid', () => {
    const invalidLat = {
      location: {
        type: 'Point',
        coordinates: [0, 95], // lat > 90
      },
    };
    expect(parcelCentroidLatLon(invalidLat)).toBeNull();

    const invalidLon = {
      location: {
        type: 'Point',
        coordinates: [190, 45], // lon > 180
      },
    };
    expect(parcelCentroidLatLon(invalidLon)).toBeNull();

    const nonGeometry = {
      location: {
        type: 'LineString',
        coordinates: [[0, 0], [1, 1]],
      },
    };
    expect(parcelCentroidLatLon(nonGeometry)).toBeNull();
  });
});

describe('applyParcelPrefill', () => {
  const parcels = [
    {
      id: 'urn:ngsi-ld:AgriParcel:field-1',
      location: {
        type: 'Point',
        coordinates: [-2.5, 43.1],
      },
    },
    {
      id: 'urn:ngsi-ld:AgriParcel:field-2',
      location: {
        type: 'Point',
        coordinates: [-1.2, 42.8],
      },
    },
    {
      id: 'urn:ngsi-ld:AgriParcel:no-geom',
    },
  ];

  it('prefills parcelId, coordinates, and default depths on empty form', () => {
    const initialForm: Record<string, string> = {
      parcelId: '',
      lat: '',
      lon: '',
      depthFrom: '',
      depthTo: '',
      sand: '',
    };

    const { nextForm, autoCoords } = applyParcelPrefill(
      initialForm,
      'urn:ngsi-ld:AgriParcel:field-1',
      parcels,
      null,
    );

    expect(nextForm.parcelId).toBe('urn:ngsi-ld:AgriParcel:field-1');
    expect(nextForm.lat).toBe('43.100000');
    expect(nextForm.lon).toBe('-2.500000');
    expect(nextForm.depthFrom).toBe('0');
    expect(nextForm.depthTo).toBe('30');
    expect(autoCoords).toEqual({ lat: '43.100000', lon: '-2.500000' });
  });

  it('preserves existing depthFrom and depthTo if already set', () => {
    const prevForm: Record<string, string> = {
      parcelId: '',
      lat: '',
      lon: '',
      depthFrom: '15',
      depthTo: '45',
    };

    const { nextForm } = applyParcelPrefill(
      prevForm,
      'urn:ngsi-ld:AgriParcel:field-1',
      parcels,
      null,
    );

    expect(nextForm.depthFrom).toBe('15');
    expect(nextForm.depthTo).toBe('45');
  });

  it('does not default depths when selecting empty parcelId', () => {
    const prevForm: Record<string, string> = {
      parcelId: 'urn:ngsi-ld:AgriParcel:field-1',
      lat: '43.100000',
      lon: '-2.500000',
      depthFrom: '',
      depthTo: '',
    };

    const { nextForm, autoCoords } = applyParcelPrefill(
      prevForm,
      '',
      parcels,
      { lat: '43.100000', lon: '-2.500000' },
    );

    expect(nextForm.parcelId).toBe('');
    expect(nextForm.depthFrom).toBe('');
    expect(nextForm.depthTo).toBe('');
    expect(autoCoords).toBeNull();
  });

  it('updates coordinates when switching parcels if current coordinates were auto-filled', () => {
    const prevForm: Record<string, string> = {
      parcelId: 'urn:ngsi-ld:AgriParcel:field-1',
      lat: '43.100000',
      lon: '-2.500000',
      depthFrom: '0',
      depthTo: '30',
    };
    const prevAuto = { lat: '43.100000', lon: '-2.500000' };

    const { nextForm, autoCoords } = applyParcelPrefill(
      prevForm,
      'urn:ngsi-ld:AgriParcel:field-2',
      parcels,
      prevAuto,
    );

    expect(nextForm.parcelId).toBe('urn:ngsi-ld:AgriParcel:field-2');
    expect(nextForm.lat).toBe('42.800000');
    expect(nextForm.lon).toBe('-1.200000');
    expect(autoCoords).toEqual({ lat: '42.800000', lon: '-1.200000' });
  });

  it('does NOT overwrite user-typed coordinates when changing parcel', () => {
    const prevForm: Record<string, string> = {
      parcelId: 'urn:ngsi-ld:AgriParcel:field-1',
      lat: '43.999999', // User manually edited lat
      lon: '-2.500000',
      depthFrom: '0',
      depthTo: '30',
    };
    const prevAuto = { lat: '43.100000', lon: '-2.500000' };

    const { nextForm, autoCoords } = applyParcelPrefill(
      prevForm,
      'urn:ngsi-ld:AgriParcel:field-2',
      parcels,
      prevAuto,
    );

    expect(nextForm.parcelId).toBe('urn:ngsi-ld:AgriParcel:field-2');
    // lat was user-typed, so coordinates should not be replaced
    expect(nextForm.lat).toBe('43.999999');
    expect(nextForm.lon).toBe('-2.500000');
    expect(autoCoords).toBeNull();
  });

  it('handles parcel with no geometry gracefully', () => {
    const prevForm: Record<string, string> = {
      parcelId: '',
      lat: '',
      lon: '',
      depthFrom: '',
      depthTo: '',
    };

    const { nextForm, autoCoords } = applyParcelPrefill(
      prevForm,
      'urn:ngsi-ld:AgriParcel:no-geom',
      parcels,
      null,
    );

    expect(nextForm.parcelId).toBe('urn:ngsi-ld:AgriParcel:no-geom');
    expect(nextForm.lat).toBe('');
    expect(nextForm.lon).toBe('');
    expect(nextForm.depthFrom).toBe('0');
    expect(nextForm.depthTo).toBe('30');
    expect(autoCoords).toBeNull();
  });
});
