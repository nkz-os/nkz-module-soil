"""Water-content limits for tillage and sowing (the "tempero" range) of a horizon.

Wet limit: water content at an air-filled porosity of 0.10 m3/m3, i.e.
saturation - 0.10 (Obour 2018, PhD thesis, Aarhus University, p. 45; Obour et
al. 2019, Soil & Tillage Research). The authors call the fixed 0.10 "somewhat
arbitrary"; it is used as published.

Dry limit: permanent wilting point (-1500 kPa, Saxton & Rawls 2006), below which
a seed cannot take up water. This is a physical definition chosen for the
platform, not a published tillage limit.

Both limits are volumetric (m3/m3) and come from the same Saxton-Rawls horizon
values the module already derives, so consumers compare their soil moisture
against them instead of keeping thresholds of their own.
"""

from __future__ import annotations

METHOD_VERSION = "1"

WORKABILITY_METHOD = {
    "version": METHOD_VERSION,
    "wet": (
        "saturation - 0.10 m3/m3 (air-filled porosity 0.10; Obour 2018 PhD thesis, "
        "Aarhus Univ., p.45; Obour et al. 2019 Soil Till. Res.)"
    ),
    "dry": (
        "permanent wilting point, -1500 kPa (Saxton & Rawls 2006); physical definition "
        "chosen by the platform owner, not a published tillage limit"
    ),
}

AIR_FILLED_POROSITY_AT_WET_LIMIT = 0.10


def tillage_limits(
    saturation: float | None, wilting_point: float | None
) -> tuple[float | None, float | None]:
    """(wet, dry) limits in m3/m3, or (None, None) when they cannot be derived.

    A horizon whose wet limit does not lie above its dry limit has no workable
    range; it gets no limits rather than an inverted pair.
    """
    if saturation is None or wilting_point is None:
        return None, None
    wet = round(saturation - AIR_FILLED_POROSITY_AT_WET_LIMIT, 3)
    dry = round(wilting_point, 3)
    if wet <= dry:
        return None, None
    return wet, dry
