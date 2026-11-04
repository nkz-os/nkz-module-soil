"""AgriSoilSample (Smart Data Models proposal) <-> the soil API's analysis shape.

One table, used in both directions, is the single source of the name and unit
mapping. The broker stores the SDM model: one entity per sampled depth, depths in
m, fractions 0-1, bulk density kg/m3, penetration resistance Pa, ``soilPh``,
camelCase method names, ``dateSampled`` at noon UTC (the day never shifts across
time zones) and ``observedAt`` = ``dateSampled`` on every result, so each result
lands in the time series at the sampling instant. The HTTP API keeps answering as
before (cm, %, g/cm3, MPa, ``ph``, snake_case methods), so FaST and the soil UI do
not change.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable
from datetime import UTC, datetime

from nkz_soil.config import CONTEXT_URL

ENTITY_TYPE = "AgriSoilSample"
_DIGITS = 9  # rounding after unit conversion: 45 % -> 0.45 -> 45, never 45.00000000000001

# input (snake_case) -> (API horizon key, SDM attribute, SDM value = API value * factor)
FIELDS: tuple[tuple[str, str, str, float], ...] = (
    ("sand", "sand", "sand", 0.01),
    ("silt", "silt", "silt", 0.01),
    ("clay", "clay", "clay", 0.01),
    ("organic_carbon", "organicCarbon", "organicCarbon", 0.01),
    ("organic_matter", "organicMatter", "organicMatter", 0.01),
    ("total_nitrogen", "totalNitrogen", "totalNitrogen", 0.01),
    ("carbonates", "carbonates", "carbonates", 0.01),
    ("active_lime", "activeLime", "activeLime", 0.01),
    ("coarse_fragments", "coarseFragments", "coarseFragments", 0.01),
    ("bulk_density", "bulkDensity", "bulkDensity", 1000.0),               # g/cm3 -> kg/m3
    ("penetration_resistance", "penetrationResistance", "penetrationResistance", 1e6),  # MPa -> Pa
    ("ph", "ph", "soilPh", 1.0),
    ("cec", "cec", "cec", 1.0),                                           # cmol(+)/kg
    ("nitrate_n", "nitrateN", "nitrateN", 1.0),                           # mg/kg
    ("ammonium_n", "ammoniumN", "ammoniumN", 1.0),
    ("phosphorus_available", "phosphorusAvailable", "phosphorusAvailable", 1.0),
    ("potassium_exchangeable", "potassiumExchangeable", "potassiumExchangeable", 1.0),
)
# input (snake_case) -> (API horizon key, SDM attribute); values snake_case <-> camelCase
METHOD_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("phosphorus_method", "phosphorusMethod", "phosphorusMethod"),
    ("potassium_method", "potassiumMethod", "potassiumMethod"),
)
# entity-level attributes: input -> (API analysis key, SDM attribute)
_TEXT_ATTRS = (("laboratory_reference", "laboratoryReference", "sampleCode"),
               ("operator", "operator", "operator"))


def _round(value: float) -> float | int:
    r = round(value, _DIGITS)
    return int(r) if float(r).is_integer() and abs(r) < 1e15 else r


def _camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


def _snake(camel: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", camel).lower()


def _noon(sampling_date: str | None) -> str:
    day = sampling_date or datetime.now(UTC).date().isoformat()
    return f"{day}T12:00:00Z"


def sample_id(tenant: str, cleaned: dict) -> str:
    """Deterministic id: re-importing the same row updates the same entity."""
    key = "|".join([
        cleaned.get("parcel_id") or "",
        f"{float(cleaned['lat']):.6f}", f"{float(cleaned['lon']):.6f}",
        cleaned.get("sampling_date") or "",
        str(cleaned["depth_from"]), str(cleaned["depth_to"]),
        cleaned.get("laboratory_reference") or "",
    ])
    return f"urn:ngsi-ld:{ENTITY_TYPE}:{tenant}:{hashlib.sha256(key.encode()).hexdigest()[:16]}"


def _parcel_urn(parcel_id: str) -> str:
    return parcel_id if parcel_id.startswith("urn:") else f"urn:ngsi-ld:AgriParcel:{parcel_id}"


def to_entity(tenant: str, cleaned: dict) -> dict:
    """Normalized NGSI-LD AgriSoilSample for one sampled depth; absent values are omitted."""
    observed = _noon(cleaned.get("sampling_date"))

    def result(value):
        return {"type": "Property", "value": value, "observedAt": observed}

    entity: dict = {
        "id": sample_id(tenant, cleaned),
        "type": ENTITY_TYPE,
        "@context": [CONTEXT_URL],
        "location": {"type": "GeoProperty",
                     "value": {"type": "Point", "coordinates": [cleaned["lon"], cleaned["lat"]]}},
        "dateSampled": {"type": "Property", "value": {"@type": "DateTime", "@value": observed}},
        "depthFrom": {"type": "Property", "value": _round(cleaned["depth_from"] / 100)},
        "depthTo": {"type": "Property", "value": _round(cleaned["depth_to"] / 100)},
    }
    for name, _key, attr, factor in FIELDS:
        if cleaned.get(name) is not None:
            entity[attr] = result(_round(float(cleaned[name]) * factor))
    for name, _key, attr in METHOD_FIELDS:
        if cleaned.get(name):
            entity[attr] = result(_camel(cleaned[name]))
    for name, _key, attr in _TEXT_ATTRS:
        if cleaned.get(name):
            entity[attr] = {"type": "Property", "value": cleaned[name]}
    if cleaned.get("number_of_subsamples") is not None:
        entity["numberOfSubsamples"] = {"type": "Property", "value": int(cleaned["number_of_subsamples"])}
    if cleaned.get("parcel_id"):
        entity["hasAgriParcel"] = {"type": "Relationship", "object": _parcel_urn(cleaned["parcel_id"])}
    if cleaned.get("zone_id"):
        entity["hasAgriManagementZone"] = {"type": "Relationship", "object": cleaned["zone_id"]}
    return entity


def _value(entity: dict, attr: str):
    v = entity.get(attr)
    if isinstance(v, dict):
        v = v.get("value", v.get("object"))
    if isinstance(v, dict) and "@value" in v:
        v = v["@value"]
    return v


def _number(v) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


def to_horizon(entity: dict) -> dict:
    """API horizon (cm, %, g/cm3, MPa, ph, snake_case methods) of one AgriSoilSample."""
    h: dict = {}
    for attr, key in (("depthFrom", "depthFrom"), ("depthTo", "depthTo")):
        v = _number(_value(entity, attr))
        if v is not None:
            h[key] = _round(v * 100)
    for _name, key, attr, factor in FIELDS:
        v = _number(_value(entity, attr))
        if v is not None:
            h[key] = _round(v / factor)
    for _name, key, attr in METHOD_FIELDS:
        v = _value(entity, attr)
        if isinstance(v, str) and v:
            h[key] = _snake(v)
    return h


def _date(entity: dict) -> str | None:
    v = _value(entity, "dateSampled")
    return v[:10] if isinstance(v, str) and len(v) >= 10 else None


def _point(entity: dict) -> tuple[float, float] | None:
    loc = _value(entity, "location")
    coords = loc.get("coordinates") if isinstance(loc, dict) else None
    if isinstance(coords, list) and len(coords) >= 2 and all(_number(c) is not None for c in coords[:2]):
        return float(coords[1]), float(coords[0])
    return None


def to_analysis(entities: Iterable[dict], linked_by: str = "hasAgriParcel") -> list[dict]:
    """Legacy ``/lab-analyses`` entries: the depths of one core (same date, place and
    sample code) form one analysis, horizons sorted by depth. The analysis id is the
    id of its shallowest depth, so it stays stable while that depth exists."""
    groups: dict[tuple, list[dict]] = {}
    for e in entities:
        point = _point(e)
        key = (_date(e), (round(point[0], 6), round(point[1], 6)) if point else None,
               _value(e, "sampleCode"))
        groups.setdefault(key, []).append(e)
    out = []
    for (day, _p, code), members in groups.items():
        members.sort(key=lambda m: (_number(_value(m, "depthFrom")) or 0.0, m.get("id", "")))
        first = members[0]
        point = _point(first)
        out.append({
            "id": first.get("id"),
            "samplingDate": day,
            "laboratoryReference": code,
            "operator": _value(first, "operator"),
            "location": {"lat": point[0], "lon": point[1]} if point else None,
            "linkedBy": linked_by,
            "dataSource": "lab_analysis",
            "horizons": [to_horizon(m) for m in members],
        })
    return out
