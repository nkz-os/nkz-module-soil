"""USDA soil texture triangle classification from sand/silt/clay percentages.

Returns one of the 12 USDA classes as a kebab-case slug, or None if the
fractions do not sum to ~100% (tolerance matches the API validators, ±3).
Boundaries follow the standard USDA textural triangle (NRCS Soil Survey Manual).

This is computed by Nekazari from the merged fractions; when those fractions
derive from a non-redistributable source (e.g. JRC LUCAS texture rasters) the
class is still emittable because it is our own derived work, not the source data.
"""
from __future__ import annotations


def usda_texture_class(sand: float | None, silt: float | None, clay: float | None) -> str | None:
    if sand is None or silt is None or clay is None:
        return None
    total = sand + silt + clay
    if total < 97 or total > 103:
        return None

    if clay >= 40 and silt >= 40:
        return "silty-clay"
    if clay >= 40 and sand <= 45 and silt < 40:
        return "clay"
    if clay >= 35 and sand > 45:
        return "sandy-clay"
    if 27 <= clay < 40 and sand <= 20:
        return "silty-clay-loam"
    if 27 <= clay < 40 and 20 < sand <= 45:
        return "clay-loam"
    if 20 <= clay < 35 and silt < 28 and sand > 45:
        return "sandy-clay-loam"
    if silt >= 80 and clay < 12:
        return "silt"
    if (silt >= 50 and 12 <= clay < 27) or (50 <= silt < 80 and clay < 12):
        return "silt-loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "loam"
    if ((7 <= clay < 20 and sand > 52 and (silt + 2 * clay) >= 30)
            or (clay < 7 and silt < 50 and (silt + 2 * clay) >= 30)):
        return "sandy-loam"
    if (silt + 1.5 * clay) >= 15 and (silt + 2 * clay) < 30:
        return "loamy-sand"
    if (silt + 1.5 * clay) < 15:
        return "sand"
    return "loam"  # interior fallback for rare boundary gaps
