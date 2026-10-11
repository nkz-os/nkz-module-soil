"""Readers for NGSI-LD values as Orion-LD returns them."""
from __future__ import annotations


def horizons_of(entity: dict) -> list[dict]:
    """The `horizons` list of an entity, normalized or keyValues.

    Orion-LD returns a one-element array unwrapped (the object itself), so a sampling
    point with a single horizon comes back as a dict, not a list.
    """
    raw = entity.get("horizons")
    if isinstance(raw, dict) and raw.get("type") == "Property" and "value" in raw:
        raw = raw["value"]
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [h for h in raw if isinstance(h, dict)]
