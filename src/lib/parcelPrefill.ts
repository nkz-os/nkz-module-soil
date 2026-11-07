import { ngsiValue } from './ngsiValue';

export function matchParcelId(
  requested: string | null | undefined,
  parcels: ReadonlyArray<{ id: string }> | null | undefined,
): string | null {
  if (!requested || !parcels?.length) return null;
  const trimmed = requested.trim();
  if (!trimmed) return null;

  const exact = parcels.find((p) => p?.id === trimmed);
  if (exact) return exact.id;

  const short = trimmed.split(':').pop()?.trim();
  if (!short) return null;

  const matched = parcels.find((p) => {
    if (!p?.id) return false;
    if (p.id === short) return true;
    const pShort = p.id.split(':').pop()?.trim();
    return pShort === short;
  });

  return matched ? matched.id : null;
}

export function parcelCentroidLatLon(
  parcel: Record<string, unknown> | null | undefined,
): { lat: string; lon: string } | null {
  if (!parcel) return null;
  const rawLocation = parcel.location;
  const location = (
    rawLocation !== undefined
      ? ngsiValue<Record<string, unknown>>(rawLocation)
      : ('type' in parcel && 'coordinates' in parcel ? parcel : null)
  ) as Record<string, unknown> | null | undefined;

  if (!location || typeof location !== 'object') return null;

  const type = typeof location.type === 'string' ? location.type.toLowerCase() : '';
  const coords = location.coordinates;

  if (type === 'point') {
    if (!Array.isArray(coords) || coords.length < 2) return null;
    const lon = coords[0];
    const lat = coords[1];
    if (typeof lon !== 'number' || !Number.isFinite(lon) || typeof lat !== 'number' || !Number.isFinite(lat)) {
      return null;
    }
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      return null;
    }
    return {
      lat: lat.toFixed(6),
      lon: lon.toFixed(6),
    };
  }

  let ring: unknown;
  if (type === 'polygon') {
    ring = Array.isArray(coords) ? coords[0] : undefined;
  } else if (type === 'multipolygon') {
    ring = Array.isArray(coords) && Array.isArray(coords[0]) ? coords[0][0] : undefined;
  } else {
    return null;
  }

  if (!Array.isArray(ring) || ring.length === 0) return null;

  let points: [number, number][] = [];
  for (const pt of ring) {
    if (!Array.isArray(pt) || pt.length < 2) return null;
    const lon = pt[0];
    const lat = pt[1];
    if (typeof lon !== 'number' || !Number.isFinite(lon) || typeof lat !== 'number' || !Number.isFinite(lat)) {
      return null;
    }
    points.push([lon, lat]);
  }

  if (points.length === 0) return null;

  if (
    points.length > 1 &&
    points[0][0] === points[points.length - 1][0] &&
    points[0][1] === points[points.length - 1][1]
  ) {
    points = points.slice(0, -1);
  }

  if (points.length === 0) return null;

  const sumLon = points.reduce((acc, p) => acc + p[0], 0);
  const sumLat = points.reduce((acc, p) => acc + p[1], 0);
  const avgLon = sumLon / points.length;
  const avgLat = sumLat / points.length;

  if (!Number.isFinite(avgLat) || !Number.isFinite(avgLon)) return null;
  if (avgLat < -90 || avgLat > 90 || avgLon < -180 || avgLon > 180) return null;

  return {
    lat: avgLat.toFixed(6),
    lon: avgLon.toFixed(6),
  };
}

export function applyParcelPrefill(
  prevForm: Record<string, string>,
  parcelId: string,
  parcels: ReadonlyArray<Record<string, unknown>> | null | undefined,
  prevAutoCoords?: { lat: string; lon: string } | null,
): { nextForm: Record<string, string>; autoCoords: { lat: string; lon: string } | null } {
  const nextForm: Record<string, string> = { ...prevForm, parcelId };
  const parcel = parcels?.find((p) => p && p.id === parcelId);
  const coords = parcelCentroidLatLon(parcel);

  let autoCoords: { lat: string; lon: string } | null = null;
  if (coords) {
    const prevLat = prevForm.lat ?? '';
    const prevLon = prevForm.lon ?? '';
    const latCanFill = prevLat === '' || (prevAutoCoords != null && prevLat === prevAutoCoords.lat);
    const lonCanFill = prevLon === '' || (prevAutoCoords != null && prevLon === prevAutoCoords.lon);

    if (latCanFill && lonCanFill) {
      nextForm.lat = coords.lat;
      nextForm.lon = coords.lon;
      autoCoords = coords;
    }
  }

  if (parcelId) {
    if ((nextForm.depthFrom ?? '') === '') {
      nextForm.depthFrom = '0';
    }
    if ((nextForm.depthTo ?? '') === '') {
      nextForm.depthTo = '30';
    }
  }

  return { nextForm, autoCoords };
}
