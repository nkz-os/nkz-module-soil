import pytest
from nkz_soil.models.fertility import (
    FERTILITY_FIELDS,
    K_METHODS,
    P_METHODS,
    fertility_horizon_entries,
    validate_fertility,
    validate_sampling_date,
)

FULL = {
    "organic_matter": 2.1, "total_nitrogen": 0.12, "nitrate_n": 14.0, "ammonium_n": 2.0,
    "phosphorus_available": 18.0, "phosphorus_method": "olsen",
    "potassium_exchangeable": 240.0, "potassium_method": "ammonium_acetate",
    "carbonates": 25.0, "active_lime": 8.0,
}


def test_full_analysis_is_valid():
    assert validate_fertility(FULL) == []


def test_empty_is_valid():
    assert validate_fertility({}) == []


@pytest.mark.parametrize("name,value", [
    ("organic_matter", -1.0), ("phosphorus_available", 501.0),
    ("potassium_exchangeable", 3001.0), ("nitrate_n", 600.0),
])
def test_out_of_range_rejected(name, value):
    values = {name: value}
    if name == "phosphorus_available":
        values["phosphorus_method"] = "olsen"
    if name == "potassium_exchangeable":
        values["potassium_method"] = "ammonium_acetate"
    errors = validate_fertility(values)
    assert len(errors) == 1
    assert FERTILITY_FIELDS[name][0] in errors[0]


def test_bool_is_not_a_number():
    assert validate_fertility({"carbonates": True}) == ["carbonates must be 0-100"]


def test_p_without_method_rejected():
    assert validate_fertility({"phosphorus_available": 12.0}) == [
        "phosphorusMethod is required when phosphorusAvailable is set"]


def test_unknown_p_method_rejected():
    errors = validate_fertility({"phosphorus_available": 12.0, "phosphorus_method": "magic"})
    assert len(errors) == 1 and errors[0].startswith("phosphorusMethod must be one of")


def test_method_without_value_rejected():
    assert validate_fertility({"potassium_method": "ammonium_acetate"}) == [
        "potassiumMethod given without potassiumExchangeable"]


def test_active_lime_above_carbonates_rejected():
    assert validate_fertility({"carbonates": 5.0, "active_lime": 9.0}) == [
        "activeLime cannot exceed carbonates"]


def test_horizon_entries_camel_case_without_none():
    assert fertility_horizon_entries({
        "organic_matter": 2.0, "nitrate_n": None,
        "phosphorus_available": 9.0, "phosphorus_method": "bray1",
    }) == {"organicMatter": 2.0, "phosphorusAvailable": 9.0, "phosphorusMethod": "bray1"}


def test_p_methods_are_the_engine_table():
    # Same keys as the FaST engine's Olsen conversion (Villalobos et al. 2020, Table 5).
    assert P_METHODS == {"olsen", "bray1", "mehlich3", "ammonium_lactate",
                         "ammonium_acetate_edta", "calcium_lactate",
                         "calcium_lactate_acetate", "water", "cacl2"}
    assert "ammonium_acetate" in K_METHODS


@pytest.mark.parametrize("value", ["2026-09-30", "2024-02-29"])
def test_iso_sampling_date_accepted(value):
    assert validate_sampling_date(value, required=True) == []


@pytest.mark.parametrize("value", ["15/03/2025", "2025-3-15", "2025-02-30", "20250315"])
def test_non_iso_sampling_date_rejected(value):
    assert validate_sampling_date(value, required=False) == ["samplingDate must be YYYY-MM-DD"]


def test_sampling_date_required_for_fertility_values():
    assert validate_sampling_date(None, required=True) == [
        "samplingDate is required for laboratory fertility values"]
    assert validate_sampling_date(None, required=False) == []
