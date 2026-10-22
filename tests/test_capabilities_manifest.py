from pathlib import Path

import yaml

CAP = Path(__file__).resolve().parents[1] / "capabilities.yaml"


def test_usda_texture_class_declared_and_restricted_source_noted():
    doc = yaml.safe_load(CAP.read_text())
    soil = next(p for p in doc["publishes"] if p["entityType"] == "AgriSoilExtended")
    attrs = {a["name"]: a for a in soil["attributes"]}
    assert "usdaTextureClass" in attrs
    assert attrs["usdaTextureClass"]["confidence"] == "derived"
    # LUCAS-Texture (restricted) contributes to the JRC-derived emitted outputs
    assert "LUCAS-Texture" in attrs["availableWaterCapacity"]["sources"]
