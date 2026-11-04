"""Leaf (plant tissue) analyses: lab units in the CSV, SDM units in the broker (AgriPlantSample)."""
import pytest
from nkz_soil.models.agri_plant_sample import (
    UnitError,
    convert,
    parse_header,
    sample_id,
    to_entity,
    to_rows,
)

PARCEL = "urn:ngsi-ld:AgriParcel:demo-parcel-001"
T1 = "urn:ngsi-ld:AgriPlant:tenant-a:demo-parcel-001:T-1"
T2 = "urn:ngsi-ld:AgriPlant:tenant-a:demo-parcel-001:T-2"


def _row(**over):
    row = {"plant_codes": ["T-1"], "date_sampled": "2026-07-15", "plant_tissue": "leaf",
           "sample_code": "LAB-1", "results": {}, "other_results": []}
    row.update(over)
    return row


def test_parse_header_named_results_and_units():
    assert parse_header("N (%)") == ("nitrogen", "N", "%")
    assert parse_header("Fe (ppm)") == ("iron", "Fe", "ppm")
    assert parse_header("potassium") == ("potassium", "potassium", None)
    assert parse_header("Mo (mg/kg)") == (None, "Mo", "mg/kg")
    assert parse_header("sulfur (g/kg)") == ("sulphur", "sulfur", "g/kg")


def test_percent_and_g_per_kg_to_fraction():
    assert convert("nitrogen", 1.8, "%") == 0.018
    assert convert("potassium", 9.5, "g/kg") == 0.0095
    assert convert("nitrogen", 1.8, None) == 0.018  # bare macro column: % by default


def test_ppm_is_mg_per_kg():
    assert convert("iron", 85, "ppm") == 85
    assert convert("boron", 22.5, "mg/kg") == 22.5
    assert convert("zinc", 0.002, "%") == 20  # 0.002 % = 20 mg/kg
    assert convert("iron", 85, None) == 85  # bare micro column: mg/kg by default


def test_unknown_unit_raises_naming_column():
    with pytest.raises(UnitError) as exc:
        convert("calcium", 12, "meq/100g", column="Ca (meq/100g)")
    assert "Ca (meq/100g)" in str(exc.value)


def test_other_results_with_unit_code():
    e = to_entity("tenant-a", PARCEL, _row(other_results=[
        {"name": "Mo", "value": 0.4, "unit": "mg/kg"}, {"name": "Si", "value": 1.2, "unit": "%"}]), [T1])
    assert e["otherResults"]["value"] == [
        {"name": "Mo", "value": 0.4, "unitCode": "NA"}, {"name": "Si", "value": 1.2, "unitCode": "P1"}]


def test_single_tree_relationship_is_string():
    e = to_entity("tenant-a", PARCEL, _row(), [T1])
    assert e["hasAgriPlant"] == {"type": "Relationship", "object": T1}
    assert e["hasAgriParcel"] == {"type": "Relationship", "object": PARCEL}


def test_composite_is_list():
    e = to_entity("tenant-a", PARCEL, _row(plant_codes=["T-2", "T-1"]), [T2, T1])
    assert e["hasAgriPlant"] == {"type": "Relationship", "object": [T2, T1]}


def test_observed_at_noon_and_typed_dates():
    e = to_entity("tenant-a", PARCEL, _row(results={"nitrogen": 0.018, "iron": 85}, date_analysed="2026-08-01"), [T1])
    assert e["dateSampled"]["value"] == {"@type": "DateTime", "@value": "2026-07-15T12:00:00Z"}
    assert e["dateAnalysed"]["value"] == {"@type": "DateTime", "@value": "2026-08-01T12:00:00Z"}
    for attr in ("nitrogen", "iron"):
        assert e[attr]["observedAt"] == "2026-07-15T12:00:00Z"
    assert e["plantTissue"]["value"] == "leaf" and e["sampleCode"]["value"] == "LAB-1"


def test_id_deterministic_and_code_order_free():
    a = sample_id("tenant-a", PARCEL, ["T-1", "T-2"], "2026-07-15", "leaf", "LAB-1")
    assert a == sample_id("tenant-a", PARCEL, ["T-2", "T-1"], "2026-07-15", "leaf", "LAB-1")
    assert a.startswith("urn:ngsi-ld:AgriPlantSample:tenant-a:") and len(a.rsplit(":", 1)[1]) == 16
    assert a != sample_id("tenant-a", PARCEL, ["T-1", "T-2"], "2026-07-15", "petiole", "LAB-1")
    assert to_entity("tenant-a", PARCEL, _row(plant_codes=["T-2", "T-1"]), [T2, T1])["id"] == a


def test_roundtrip_to_rows():
    e = to_entity("tenant-a", PARCEL, _row(results={"nitrogen": 0.018, "potassium": 0.0095, "iron": 85.0},
                                           phenological_stage="BBCH 75", number_of_subsamples=40), [T1])
    r = to_rows(e)
    assert r["nitrogen (%)"] == 1.8 and r["potassium (%)"] == 0.95 and r["iron (mg/kg)"] == 85
    assert r["dateSampled"] == "2026-07-15" and r["plantCodes"] == "T-1"
    assert r["phenologicalStage"] == "BBCH 75" and r["numberOfSubsamples"] == 40
