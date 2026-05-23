"""Validate every SDM proposal example against its schema."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from jsonschema import Draft7Validator

SDM_DIR = Path(__file__).resolve().parents[2] / "sdm"
ENTITIES = ["AgriSoilExtended", "SoilSamplingPoint", "SoilSurvey", "SoilDerivedRaster"]


@pytest.mark.parametrize("entity", ENTITIES)
def test_schema_is_valid_draft07(entity: str) -> None:
    schema_path = SDM_DIR / entity / "schema.json"
    schema = json.loads(schema_path.read_text())
    Draft7Validator.check_schema(schema)


@pytest.mark.parametrize("entity", ENTITIES)
def test_example_matches_schema(entity: str) -> None:
    schema = json.loads((SDM_DIR / entity / "schema.json").read_text())
    example = json.loads((SDM_DIR / entity / "example.json").read_text())
    # Resolve $ref to common-schema by stripping allOf refs that we can't fetch offline,
    # then re-check inline-property block only.
    inline = next((p for p in schema["allOf"] if "properties" in p), None)
    assert inline is not None, f"{entity} schema missing inline properties block"
    inline_schema = {"type": "object", **{k: v for k, v in inline.items() if k != "$ref"}}
    Draft7Validator(inline_schema).validate(example)
