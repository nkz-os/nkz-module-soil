"""AgriPlantSample (Smart Data Models proposal) <-> leaf (plant tissue) lab reports.

Labs report macronutrients in % (or g/kg) and micronutrients in mg/kg (or ppm). The
broker stores the SDM model: macronutrients as 0-1 fractions, micronutrients in mg/kg,
``dateSampled`` at noon UTC and ``observedAt`` = ``dateSampled`` on every result, so each
result lands in the time series at the sampling instant. One table here is the single
source of names and units, used by the import and by the export.
"""
from __future__ import annotations

import hashlib
import math
import re

ENTITY_TYPE = "AgriPlantSample"
TISSUES = ("leaf", "petiole", "fruit", "flower", "shoot", "wholePlant", "other")
_DIGITS = 9

# SDM attribute -> (kind, aliases); kind "fraction" (macro, default %) or "mgkg" (micro)
_RESULTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "nitrogen": ("fraction", ("n", "nitrogen", "nitrogeno", "nitrógeno")),
    "phosphorus": ("fraction", ("p", "phosphorus", "fosforo", "fósforo")),
    "potassium": ("fraction", ("k", "potassium", "potasio")),
    "calcium": ("fraction", ("ca", "calcium", "calcio")),
    "magnesium": ("fraction", ("mg", "magnesium", "magnesio")),
    "sulphur": ("fraction", ("s", "sulphur", "sulfur", "azufre")),
    "chloride": ("fraction", ("cl", "chloride", "cloro", "cloruro")),
    "iron": ("mgkg", ("fe", "iron", "hierro")),
    "manganese": ("mgkg", ("mn", "manganese", "manganeso")),
    "zinc": ("mgkg", ("zn", "zinc")),
    "copper": ("mgkg", ("cu", "copper", "cobre")),
    "boron": ("mgkg", ("b", "boron", "boro")),
    "sodium": ("mgkg", ("na", "sodium", "sodio")),
}
_ALIAS = {alias: attr for attr, (_k, aliases) in _RESULTS.items() for alias in aliases}
# accepted units -> factor to mg/kg
_UNIT_TO_MGKG = {"%": 10_000.0, "g/kg": 1_000.0, "mg/kg": 1.0, "ppm": 1.0}
_UNIT_CODE = {"%": "P1", "g/kg": "GK", "mg/kg": "NA", "ppm": "NA"}
_CODE_UNIT = {"P1": "%", "GK": "g/kg", "NA": "mg/kg"}
_HEADER = re.compile(r"^\s*(.+?)\s*\(\s*([^)]+?)\s*\)\s*$")
_LAB_UNIT = {"fraction": "%", "mgkg": "mg/kg"}


class UnitError(ValueError):
    """A result column with a unit this import does not convert."""


def _round(v: float) -> float | int:
    r = round(v, _DIGITS)
    return int(r) if float(r).is_integer() and abs(r) < 1e15 else r


def _norm_unit(unit: str | None) -> str | None:
    return None if unit is None else unit.strip().lower().replace(" ", "")


def parse_header(column: str) -> tuple[str | None, str, str | None]:
    """(SDM attribute or None, name as written, unit as written or None)."""
    m = _HEADER.match(column)
    name, unit = (m.group(1), m.group(2)) if m else (column.strip(), None)
    return _ALIAS.get(name.strip().lower()), name.strip(), unit


def convert(attr: str, value: float, unit: str | None, column: str | None = None) -> float | int:
    """Lab value -> SDM value (fraction for macronutrients, mg/kg for micronutrients)."""
    kind = _RESULTS[attr][0]
    u = _norm_unit(unit) or _LAB_UNIT[kind]
    if u not in _UNIT_TO_MGKG:
        raise UnitError(f"unknown unit in column {column or attr}: {unit}")
    mgkg = float(value) * _UNIT_TO_MGKG[u]
    return _round(mgkg / 1_000_000.0 if kind == "fraction" else mgkg)


def unit_code(unit: str) -> str:
    u = _norm_unit(unit)
    if u not in _UNIT_CODE:
        raise UnitError(f"unknown unit: {unit}")
    return _UNIT_CODE[u]


def check_unit(unit: str, column: str) -> None:
    """Raise UnitError naming the column when its unit is not one this import stores."""
    if _norm_unit(unit) not in _UNIT_CODE:
        raise UnitError(f"unknown unit in column {column}: {unit}")


def sample_id(tenant: str, parcel_urn: str, codes: list[str], day: str, tissue: str, code: str) -> str:
    key = "|".join([parcel_urn, ",".join(sorted(codes)), day, tissue, code])
    return f"urn:ngsi-ld:{ENTITY_TYPE}:{tenant}:{hashlib.sha256(key.encode()).hexdigest()[:16]}"


def _dt(day: str) -> dict:
    return {"@type": "DateTime", "@value": f"{day}T12:00:00Z"}


def to_entity(tenant: str, parcel_urn: str, row: dict, plant_ids: list[str],
              location: dict | None = None) -> dict:
    """Normalized NGSI-LD AgriPlantSample. ``row``: plant_codes, date_sampled (YYYY-MM-DD),
    plant_tissue, sample_code, results {attr: SDM value}, other_results [{name, value, unit}],
    optional phenological_stage, number_of_subsamples, laboratory, date_analysed, analysis_method."""
    day = row["date_sampled"]
    observed = f"{day}T12:00:00Z"
    e: dict = {
        "id": sample_id(tenant, parcel_urn, row["plant_codes"], day, row["plant_tissue"], row["sample_code"]),
        "type": ENTITY_TYPE,
        "hasAgriPlant": {"type": "Relationship", "object": plant_ids[0] if len(plant_ids) == 1 else list(plant_ids)},
        "hasAgriParcel": {"type": "Relationship", "object": parcel_urn},
        "dateSampled": {"type": "Property", "value": _dt(day)},
        "plantTissue": {"type": "Property", "value": row["plant_tissue"]},
        "sampleCode": {"type": "Property", "value": row["sample_code"]},
    }
    if location:
        e["location"] = {"type": "GeoProperty", "value": location}
    for key, attr in (("phenological_stage", "phenologicalStage"), ("laboratory", "laboratory"),
                      ("analysis_method", "analysisMethod")):
        if row.get(key):
            e[attr] = {"type": "Property", "value": row[key]}
    if row.get("number_of_subsamples") is not None:
        e["numberOfSubsamples"] = {"type": "Property", "value": int(row["number_of_subsamples"])}
    if row.get("date_analysed"):
        e["dateAnalysed"] = {"type": "Property", "value": _dt(row["date_analysed"])}
    for attr, value in row.get("results", {}).items():
        e[attr] = {"type": "Property", "value": value, "observedAt": observed}
    others = [{"name": o["name"], "value": o["value"], "unitCode": unit_code(o["unit"])}
              for o in row.get("other_results", [])]
    if others:
        e["otherResults"] = {"type": "Property", "value": others, "observedAt": observed}
    return e


def _value(entity: dict, attr: str):
    v = entity.get(attr)
    if isinstance(v, dict):
        v = v.get("value", v.get("object"))
    if isinstance(v, dict) and "@value" in v:
        v = v["@value"]
    return v


def to_rows(entity: dict) -> dict:
    """One export row in lab units (% for macronutrients, mg/kg for micronutrients)."""
    plants = _value(entity, "hasAgriPlant")
    plants = plants if isinstance(plants, list) else [plants] if plants else []
    day = _value(entity, "dateSampled")
    row: dict = {
        "sampleId": entity.get("id"),
        "plantCodes": ";".join(str(p).rsplit(":", 1)[-1] for p in plants),
        "dateSampled": day[:10] if isinstance(day, str) else None,
        "plantTissue": _value(entity, "plantTissue"),
        "sampleCode": _value(entity, "sampleCode"),
        "phenologicalStage": _value(entity, "phenologicalStage"),
        "numberOfSubsamples": _value(entity, "numberOfSubsamples"),
        "laboratory": _value(entity, "laboratory"),
        "analysisMethod": _value(entity, "analysisMethod"),
    }
    analysed = _value(entity, "dateAnalysed")
    row["dateAnalysed"] = analysed[:10] if isinstance(analysed, str) else None
    for attr, (kind, _a) in _RESULTS.items():
        v = _value(entity, attr)
        header = f"{attr} ({_LAB_UNIT[kind]})"
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            row[header] = _round(v * 100 if kind == "fraction" else v)
        else:
            row[header] = None
    for other in _value(entity, "otherResults") or []:
        if isinstance(other, dict) and other.get("name"):
            unit = _CODE_UNIT.get(str(other.get("unitCode")), str(other.get("unitCode") or ""))
            row[f"{other['name']} ({unit})"] = other.get("value")
    return row


RESULT_HEADERS = tuple(f"{a} ({_LAB_UNIT[k]})" for a, (k, _x) in _RESULTS.items())

# Attributes an import writes from the sheet: a re-import that leaves one empty removes it.
MANAGED_ATTRS = (*_RESULTS, "otherResults", "phenologicalStage", "laboratory", "analysisMethod",
                 "numberOfSubsamples", "dateAnalysed")
