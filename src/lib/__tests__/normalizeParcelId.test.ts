import { describe, it, expect } from 'vitest';
import { normalizeParcelId, parcelApiPath } from '../../lib/normalizeParcelId';

describe('normalizeParcelId', () => {
  it('strips canonical AgriParcel URN prefix', () => {
    expect(normalizeParcelId('urn:ngsi-ld:AgriParcel:da36ccd2-85d2-4c76-b552-c5c835a987c1')).toBe(
      'da36ccd2-85d2-4c76-b552-c5c835a987c1',
    );
  });

  it('encodes path segment for API calls', () => {
    expect(parcelApiPath('urn:ngsi-ld:AgriParcel:abc')).toBe('abc');
  });
});
