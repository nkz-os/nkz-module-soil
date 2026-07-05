"""No-data sentinels from raster/REST providers (SoilGrids, etc.)."""

from __future__ import annotations

# SoilGrids / ISRIC common nodata values (Float32 int16 min, legacy sentinels).
SOILGRIDS_NODATA: tuple[float, ...] = (-9999.0, -3276.8, -3.40282347e38)

_NUMERIC_HORIZON_KEYS = frozenset({
    "sand", "silt", "clay", "organicCarbon", "ph", "cec", "coarseFragments",
    "bulkDensity", "nitrogen", "fieldCapacity", "wiltingPoint", "ksatMmH",
    "penetrationResistance", "organic_carbon", "bulk_density", "coarse_fragments",
})


def is_soilgrids_nodata(value: float | int | None) -> bool:
    if value is None:
        return False
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return False
    return any(abs(fv - sentinel) < 1e-6 for sentinel in SOILGRIDS_NODATA)


def clean_nodata_value(value: float | int | None) -> float | int | None:
    return None if is_soilgrids_nodata(value) else value


def sanitize_horizon(horizon: dict) -> dict:
    """Drop provider nodata sentinels from a horizon dict (camelCase or snake)."""
    out = dict(horizon)
    for key in _NUMERIC_HORIZON_KEYS:
        if key in out:
            cleaned = clean_nodata_value(out[key])
            if cleaned is None:
                out.pop(key, None)
            else:
                out[key] = cleaned
    return out


def sanitize_horizons(horizons: list[dict]) -> list[dict]:
    return [sanitize_horizon(h) for h in horizons]
