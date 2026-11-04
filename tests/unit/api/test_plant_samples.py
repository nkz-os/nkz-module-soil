"""Leaf analyses: CSV preview/commit as AgriPlantSample, and the per-zone CSV export."""
import csv
import io
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from nkz_platform_sdk.gis import ZoneRef, Zoning
from nkz_soil.api.main import create_app

HEADERS = {"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"}
PARCEL = "urn:ngsi-ld:AgriParcel:demo-parcel-001"


def _plant(code, lon, lat):
    return {"id": f"urn:ngsi-ld:AgriPlant:tenant1:demo-parcel-001:{code}", "type": "AgriPlant",
            "plantCode": {"type": "Property", "value": code},
            "location": {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [lon, lat]}}}


PLANTS = [_plant("T-1", -1.6, 42.8), _plant("T-2", -1.5, 42.8)]
LEAF_CSV = """plantCode,dateSampled,sampleCode,phenologicalStage,N (%),K (g/kg),Fe (ppm),Mo (mg/kg)
T-1,2026-07-15,L-1,BBCH 75,1.8,9.5,85,0.4
T-1;T-2,2026-07-15,L-2,,1.6,,70,
"""


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def orion():
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    store = {"AgriPlant": list(PLANTS), "AgriPlantSample": []}

    async def query(type=None, q=None, limit=1000, offset=0, **_):
        assert q == f'hasAgriParcel=="{PARCEL}"'
        return store[type][offset:offset + limit]

    async def upsert(entities):  # options=update: attributes merge into an existing entity
        current = {e["id"]: e for e in store["AgriPlantSample"]}
        for x in entities:
            if x["id"] in current:
                current[x["id"]].update(x)
            else:
                store["AgriPlantSample"].append(dict(x))
        return {"upserted": len(entities), "errors": [], "entity_ids": [e["id"] for e in entities]}

    async def delete_attr(entity_id, attr):
        for e in store["AgriPlantSample"]:
            if e["id"] == entity_id:
                e.pop(attr, None)

    mock.query_all = AsyncMock(side_effect=query)
    mock.upsert_entities_batch = AsyncMock(side_effect=upsert)
    mock.delete_entity_attr = AsyncMock(side_effect=delete_attr)
    mock.store = store
    with patch("nkz_soil.api.routes.plant_samples.OrionClient", return_value=mock):
        yield mock


def _batch(client, text, dry_run):
    return client.post(f"/v1/soil/plant-samples/batch?parcel_id={PARCEL}&dry_run={'true' if dry_run else 'false'}",
                       files={"file": ("leaf.csv", text, "text/csv")}, headers=HEADERS)


def test_dry_run_writes_nothing(client, orion):
    r = _batch(client, LEAF_CSV, True)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [a["plantCodes"] for a in body["accepted"]] == [["T-1"], ["T-1", "T-2"]]
    assert body["created"] == 0
    orion.upsert_entities_batch.assert_not_called()


def test_commit_writes_converted_samples(client, orion):
    body = _batch(client, LEAF_CSV, False).json()
    assert body["created"] == 2
    one, composite = orion.store["AgriPlantSample"]
    assert one["nitrogen"]["value"] == 0.018 and one["potassium"]["value"] == 0.0095 and one["iron"]["value"] == 85
    assert one["otherResults"]["value"] == [{"name": "Mo", "value": 0.4, "unitCode": "NA"}]
    assert one["hasAgriPlant"]["object"] == PLANTS[0]["id"]
    assert composite["hasAgriPlant"]["object"] == [PLANTS[0]["id"], PLANTS[1]["id"]]
    assert one["location"]["value"]["coordinates"] == [-1.6, 42.8]


def test_unknown_plant_code_rejected(client, orion):
    body = _batch(client, "plantCode,dateSampled,sampleCode,N (%)\nT-9,2026-07-15,L-9,1.8\n", True).json()
    assert body["accepted"] == [] and "T-9" in body["rejected"][0]["error"]


def test_unknown_unit_rejects_row(client, orion):
    body = _batch(client, "plantCode,dateSampled,sampleCode,Ca (meq/100g)\nT-1,2026-07-15,L-1,12\n", True).json()
    assert body["rejected"][0]["row"] == 2 and "Ca (meq/100g)" in body["rejected"][0]["error"]


def test_reimport_same_ids(client, orion):
    first = [a["id"] for a in _batch(client, LEAF_CSV, False).json()["accepted"]]
    second = [a["id"] for a in _batch(client, LEAF_CSV, False).json()["accepted"]]
    assert first == second and len(orion.store["AgriPlantSample"]) == 2


def test_duplicate_rows_reported(client, orion):
    text = "plantCode,dateSampled,sampleCode,N (%)\nT-1,2026-07-15,L-1,1.8\nT-1,2026-07-15,L-1,1.9\n"
    body = _batch(client, text, True).json()
    assert len(body["accepted"]) == 1 and "duplicate of row 2" in body["rejected"][0]["error"]


def test_missing_required_columns_is_422(client, orion):
    r = _batch(client, "plantCode,N (%)\nT-1,1.8\n", True)
    assert r.status_code == 422 and "dateSampled" in r.text


def test_spanish_excel_csv(client, orion):
    body = _batch(client, "plantCode;dateSampled;sampleCode;N (%)\nT-1;2026-07-15;L-1;1,8\n", False).json()
    assert body["created"] == 1 and orion.store["AgriPlantSample"][0]["nitrogen"]["value"] == 0.018


def _square(x0, x1):
    return {"type": "Polygon", "coordinates": [[[x0, 42.7], [x1, 42.7], [x1, 42.9], [x0, 42.9], [x0, 42.7]]]}


ZONING = Zoning(run_id="manual-abc", method="manual", date="2026-06-01", zones=(
    ZoneRef(id="z1", label="T1 compost", rank=1, geometry=_square(-1.65, -1.55)),
))


def _export(client, query=""):
    r = client.get(f"/v1/soil/parcel/{PARCEL}/plant-samples/export.csv{query}", headers=HEADERS)
    assert r.status_code == 200, r.text
    return list(csv.DictReader(io.StringIO(r.text)))


def test_export_has_zone_and_units(client, orion):
    _batch(client, LEAF_CSV, False)
    with patch("nkz_soil.api.routes.plant_samples.fetch_zonings", AsyncMock(return_value=[ZONING])):
        rows = _export(client, "?zoning_run_id=manual-abc")
    one = next(r for r in rows if r["sampleCode"] == "L-1")
    assert one["zoneLabel"] == "T1 compost" and one["zoningRunId"] == "manual-abc"
    assert one["nitrogen (%)"] == "1.8" and one["iron (mg/kg)"] == "85" and one["plantCodes"] == "T-1"


def test_export_tree_outside_zones(client, orion):
    _batch(client, "plantCode,dateSampled,sampleCode,N (%)\nT-2,2026-07-15,L-5,1.8\n", False)
    with patch("nkz_soil.api.routes.plant_samples.fetch_zonings", AsyncMock(return_value=[ZONING])):
        (row,) = _export(client, "?zoning_run_id=manual-abc")
    assert row["zoneLabel"] == "" and row["nitrogen (%)"] == "1.8"


def test_export_uses_default_zoning_when_none_given(client, orion):
    auto = Zoning(run_id="veg-1", method="vegetationIndex", date="2026-05-01", zones=(
        ZoneRef(id="v1", label="Zone 1", rank=1, geometry=_square(-1.7, -1.4)),))
    _batch(client, LEAF_CSV, False)
    with patch("nkz_soil.api.routes.plant_samples.fetch_zonings", AsyncMock(return_value=[ZONING, auto])):
        rows = _export(client)
    assert {r["zoningRunId"] for r in rows} == {"veg-1"} and {r["zoneLabel"] for r in rows} == {"Zone 1"}


def test_export_unknown_zoning_is_404(client, orion):
    with patch("nkz_soil.api.routes.plant_samples.fetch_zonings", AsyncMock(return_value=[ZONING])):
        r = client.get(f"/v1/soil/parcel/{PARCEL}/plant-samples/export.csv?zoning_run_id=nope", headers=HEADERS)
    assert r.status_code == 404


def test_unsupported_unit_in_extra_column_rejects_row(client, orion):
    r = _batch(client, "plantCode,dateSampled,sampleCode,N (%),Mo (µg/g)\nT-1,2026-07-15,L-1,1.8,0.4\n", True)
    assert r.status_code == 200, r.text
    assert "Mo (µg/g)" in r.json()["rejected"][0]["error"]


def test_row_with_more_values_than_columns_rejected(client, orion):
    body = _batch(client, "plantCode,dateSampled,sampleCode,N (%)\nT-1,2026-07-15,L-1,1,8\n", True).json()
    assert body["accepted"] == [] and "more values than columns" in body["rejected"][0]["error"]


def test_cp1252_csv_accepted(client, orion):
    text = "plantCode;dateSampled;sampleCode;Fósforo (%)\nT-1;2026-07-15;L-1;0,12\n".encode("cp1252")
    r = client.post(f"/v1/soil/plant-samples/batch?parcel_id={PARCEL}&dry_run=false",
                    files={"file": ("leaf.csv", text, "text/csv")}, headers=HEADERS)
    assert r.status_code == 200, r.text
    assert orion.store["AgriPlantSample"][0]["phosphorus"]["value"] == 0.0012


@pytest.mark.parametrize("bad", ["nan", "inf", "-1"])
def test_non_finite_or_negative_result_rejected(client, orion, bad):
    body = _batch(client, f"plantCode,dateSampled,sampleCode,N (%)\nT-1,2026-07-15,L-1,{bad}\n", True).json()
    assert body["accepted"] == [] and body["rejected"]


def test_reimport_blank_value_removes_attribute(client, orion):
    _batch(client, "plantCode,dateSampled,sampleCode,N (%),Fe (ppm),phenologicalStage\nT-1,2026-07-15,L-1,1.8,85,BBCH 75\n", False)
    _batch(client, "plantCode,dateSampled,sampleCode,N (%),Fe (ppm),phenologicalStage\nT-1,2026-07-15,L-1,1.9,,\n", False)
    (s,) = orion.store["AgriPlantSample"]
    assert s["nitrogen"]["value"] == 0.019
    assert "iron" not in s and "phenologicalStage" not in s


def test_preview_marks_create_or_update(client, orion):
    text = "plantCode,dateSampled,sampleCode,N (%)\nT-1,2026-07-15,L-1,1.8\n"
    assert _batch(client, text, True).json()["accepted"][0]["action"] == "create"
    _batch(client, text, False)
    assert _batch(client, text, True).json()["accepted"][0]["action"] == "update"


def test_unmatched_header_warned_stored_as_other(client, orion):
    body = _batch(client, "plantCode,dateSampled,sampleCode,N total (%)\nT-1,2026-07-15,L-1,1.8\n", True).json()
    assert {"code": "stored_as_other", "column": "N total (%)"} in body["warnings"]


def test_export_includes_other_results_and_lab_fields(client, orion):
    _batch(client, "plantCode,dateSampled,sampleCode,laboratory,N (%),Mo (mg/kg)\nT-1,2026-07-15,L-1,Lab A,1.8,0.4\n", False)
    with patch("nkz_soil.api.routes.plant_samples.fetch_zonings", AsyncMock(return_value=[])):
        (row,) = _export(client)
    assert row["Mo (mg/kg)"] == "0.4" and row["laboratory"] == "Lab A"


def test_export_composite_across_zones_is_mixed(client, orion):
    _batch(client, "plantCode,dateSampled,sampleCode,N (%)\nT-1;T-2,2026-07-15,L-2,1.6\n", False)
    two = Zoning(run_id="manual-abc", method="manual", date="2026-06-01", zones=(
        ZoneRef(id="z1", label="T1 compost", rank=1, geometry=_square(-1.65, -1.55)),
        ZoneRef(id="z2", label="T2 control", rank=2, geometry=_square(-1.55, -1.45)),))
    with patch("nkz_soil.api.routes.plant_samples.fetch_zonings", AsyncMock(return_value=[two])):
        (row,) = _export(client, "?zoning_run_id=manual-abc")
    assert row["zoneLabel"] == "" and row["zoneMixed"] == "true"


def test_export_uses_current_tree_position(client, orion):
    _batch(client, "plantCode,dateSampled,sampleCode,N (%)\nT-2,2026-07-15,L-5,1.8\n", False)
    orion.store["AgriPlant"][1] = _plant("T-2", -1.6, 42.8)  # tree re-surveyed into zone z1
    with patch("nkz_soil.api.routes.plant_samples.fetch_zonings", AsyncMock(return_value=[ZONING])):
        (row,) = _export(client, "?zoning_run_id=manual-abc")
    assert row["zoneLabel"] == "T1 compost" and row["lon"] == "-1.6"


def test_export_without_zones(client, orion):
    _batch(client, LEAF_CSV, False)
    with patch("nkz_soil.api.routes.plant_samples.fetch_zonings", AsyncMock(return_value=[ZONING])):
        rows = _export(client, "?zoning_run_id=none")
    assert {r["zoneLabel"] for r in rows} == {""} and {r["zoningRunId"] for r in rows} == {""}
