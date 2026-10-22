"""Total porosity from bulk density, and the bound it puts on saturation.

Total porosity = 1 - bulk_density / particle_density, the definition of
porosity, with the standard mineral particle density of 2.65 g/cm3. Water can
fill at most the pore space, so a saturated water content above it is not
physical. Saxton & Rawls (2006) is a texture regression that ignores the
measured density; with a lot of organic matter it extrapolates past this bound
(seen live: saturation 0.677 against a porosity of 0.566). Organic matter
lowers the real particle density, which raises the real porosity, so the 2.65
bound is conservative.
"""

from __future__ import annotations

PARTICLE_DENSITY_G_CM3 = 2.65
# Outside this range a bulk density is a unit error or a sentinel, not a soil.
_BULK_DENSITY_RANGE_G_CM3 = (0.5, 2.2)


def total_porosity(bulk_density: float | None) -> float | None:
    """Volumetric total porosity (m3/m3), or None without a usable density."""
    if bulk_density is None:
        return None
    lo, hi = _BULK_DENSITY_RANGE_G_CM3
    if not lo <= bulk_density <= hi:
        return None
    return round(1.0 - bulk_density / PARTICLE_DENSITY_G_CM3, 3)


def bounded_saturation(
    saturation: float | None, bulk_density: float | None
) -> float | None:
    """Saturation capped at the total porosity when the density is known."""
    if saturation is None:
        return None
    porosity = total_porosity(bulk_density)
    if porosity is None:
        return saturation
    return min(saturation, porosity)
