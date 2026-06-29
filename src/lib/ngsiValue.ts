/** Unwrap NGSI-LD Property/Relationship `{ type, value }` or pass through scalars. */
export function ngsiValue<T = unknown>(field: unknown): T | undefined {
  if (field == null) return undefined;
  if (typeof field === 'object' && field !== null && 'value' in field) {
    return (field as { value: T }).value;
  }
  return field as T;
}

/** Horizons list from either flat API summary or full NGSI-LD entity. */
export function soilHorizons(entity: Record<string, unknown> | null | undefined): unknown[] {
  if (!entity) return [];
  const raw = entity.horizons;
  if (Array.isArray(raw)) return raw;
  const unwrapped = ngsiValue<unknown[]>(raw);
  return Array.isArray(unwrapped) ? unwrapped : [];
}
