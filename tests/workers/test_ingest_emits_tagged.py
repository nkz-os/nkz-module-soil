"""Ingest worker emits AgriSoilExtended with per-attribute source-tagging."""
from __future__ import annotations
from nkz_soil.workers.ingest import build_agri_soil_extended
from nkz_soil.providers.base import ProviderResult


def test_horizons_provenance_from_highest_priority_supplier():
    results = [
        ProviderResult(priority=25, attributes={"horizons": [{"depthFrom": 0, "depthTo": 30}]}, source_tag="LUCAS-2018", license="JRC-LUCAS-2018"),
        ProviderResult(priority=10, attributes={"horizons": [{"depthFrom": 0, "depthTo": 30}]}, source_tag="SoilGrids-v2", license="CC-BY-4.0"),
    ]
    e = build_agri_soil_extended(
        parcel_id="p-1",
        location={"type": "Point", "coordinates": [0, 0]},
        merged_horizons=[{"depthFrom": 0, "depthTo": 30}],
        results=results,
        parcel_version="v1",
    )
    out = e.to_ngsi()
    assert out["type"] == "AgriSoilExtended"
    assert out["horizons"]["providedBy"]["value"] == "LUCAS-2018"
    assert out["horizons"]["license"]["value"] == "JRC-LUCAS-2018"
    assert out["parcelVersionId"]["value"] == "v1"
    assert out["hasAgriParcel"]["object"] == "urn:ngsi-ld:AgriParcel:p-1"


def test_lower_priority_provenance_used_when_higher_lacks_attribute():
    results = [
        ProviderResult(priority=25, attributes={}, source_tag="LUCAS-2018", license="JRC-LUCAS-2018"),  # no horizons
        ProviderResult(priority=10, attributes={"horizons": [{"depthFrom": 0, "depthTo": 30}]}, source_tag="SoilGrids-v2", license="CC-BY-4.0"),
    ]
    e = build_agri_soil_extended(
        parcel_id="p-2",
        location={"type": "Point", "coordinates": [1, 1]},
        merged_horizons=[{"depthFrom": 0, "depthTo": 30}],
        results=results,
        parcel_version="v2",
    )
    out = e.to_ngsi()
    assert out["horizons"]["providedBy"]["value"] == "SoilGrids-v2"
