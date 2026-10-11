"""Soil fertility lab properties accepted on SoilSamplingPoint horizons.

Values are stored as the laboratory reports them. Ranges are physical plausibility
bounds, not agronomic thresholds.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date

# input name -> (horizon key, min, max)
FERTILITY_FIELDS: dict[str, tuple[str, float, float]] = {
    "organic_matter": ("organicMatter", 0.0, 100.0),                   # % w/w
    "total_nitrogen": ("totalNitrogen", 0.0, 5.0),                     # % w/w
    "nitrate_n": ("nitrateN", 0.0, 500.0),                             # mg N-NO3/kg
    "ammonium_n": ("ammoniumN", 0.0, 500.0),                           # mg N-NH4/kg
    "phosphorus_available": ("phosphorusAvailable", 0.0, 500.0),       # mg P/kg
    "potassium_exchangeable": ("potassiumExchangeable", 0.0, 3000.0),  # mg K/kg
    "carbonates": ("carbonates", 0.0, 100.0),                          # % CaCO3 eq.
    "active_lime": ("activeLime", 0.0, 100.0),                         # % CaCO3 eq.
}

# Soil P extraction methods with a published conversion to Olsen
# (Villalobos et al. 2020, Table 5).
P_METHODS = frozenset({
    "olsen", "bray1", "mehlich3", "ammonium_lactate", "ammonium_acetate_edta",
    "calcium_lactate", "calcium_lactate_acetate", "water", "cacl2",
})
K_METHODS = frozenset({
    "ammonium_acetate", "mehlich3", "ammonium_lactate", "calcium_ammonium_lactate",
})


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_method(values: Mapping[str, object], value_name: str, method_name: str,
                  allowed: frozenset[str], method_key: str, errors: list[str]) -> None:
    value_key = FERTILITY_FIELDS[value_name][0]
    value, method = values.get(value_name), values.get(method_name)
    if value is not None and not method:
        errors.append(f"{method_key} is required when {value_key} is set")
    elif method and method not in allowed:
        errors.append(f"{method_key} must be one of {', '.join(sorted(allowed))}")
    elif method and value is None:
        errors.append(f"{method_key} given without {value_key}")


def validate_fertility(values: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    for name, (key, lo, hi) in FERTILITY_FIELDS.items():
        value = values.get(name)
        if value is None:
            continue
        if not _is_number(value) or not lo <= float(value) <= hi:
            errors.append(f"{key} must be {lo:g}-{hi:g}")
    _check_method(values, "phosphorus_available", "phosphorus_method", P_METHODS,
                  "phosphorusMethod", errors)
    _check_method(values, "potassium_exchangeable", "potassium_method", K_METHODS,
                  "potassiumMethod", errors)
    lime, carbonates = values.get("active_lime"), values.get("carbonates")
    if _is_number(lime) and _is_number(carbonates) and float(lime) > float(carbonates):
        errors.append("activeLime cannot exceed carbonates")
    return errors


def fertility_horizon_entries(values: Mapping[str, object]) -> dict[str, object]:
    out: dict[str, object] = {
        key: values[name]
        for name, (key, _lo, _hi) in FERTILITY_FIELDS.items()
        if values.get(name) is not None
    }
    if values.get("phosphorus_method"):
        out["phosphorusMethod"] = values["phosphorus_method"]
    if values.get("potassium_method"):
        out["potassiumMethod"] = values["potassium_method"]
    return out


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def has_fertility_values(values: Mapping[str, object]) -> bool:
    return any(values.get(name) is not None for name in FERTILITY_FIELDS)


def validate_sampling_date(value: object, required: bool) -> list[str]:
    """ISO calendar date (YYYY-MM-DD). A lab fertility analysis needs its date: plans judge
    its age and whether it was taken before sowing."""
    if value is None or value == "":
        return ["samplingDate is required for laboratory fertility values"] if required else []
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        return ["samplingDate must be YYYY-MM-DD"]
    try:
        date.fromisoformat(value)
    except ValueError:
        return ["samplingDate must be YYYY-MM-DD"]
    return []
