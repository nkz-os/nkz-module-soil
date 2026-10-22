/**
 * Normalize AgriParcel identifiers for soil API path segments.
 * Viewer slots may pass full NGSI-LD URNs; the backend expects the UUID suffix.
 */
export function normalizeParcelId(parcelId: string): string {
  if (!parcelId) return parcelId;
  const canonical = 'urn:ngsi-ld:AgriParcel:';
  if (parcelId.startsWith(canonical)) {
    return parcelId.slice(canonical.length);
  }
  const expanded = parcelId.match(/AgriParcel:(.+)$/);
  if (expanded) return expanded[1];
  return parcelId;
}

export function parcelApiPath(parcelId: string): string {
  return encodeURIComponent(normalizeParcelId(parcelId));
}
