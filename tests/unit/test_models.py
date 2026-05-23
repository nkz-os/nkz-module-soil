import pytest
from nkz_soil.models.ngsi_ld import AgriSoil


@pytest.mark.skip(reason="awaits T20 model migration — old AgriSoil pydantic shape removed")
def test_agri_soil_valid():
    entity = AgriSoil(
        id="urn:ngsi-ld:AgriSoil:test-1",
        location={"type": "GeoProperty", "value": {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}},
        refAgriParcel={"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:parcel-1"},
        parcelVersionId={"type": "Property", "value": "v1"},
        horizons={"type": "Property", "value": [
            {"depthFrom": 0, "depthTo": 30, "sand": 45, "silt": 35, "clay": 20}
        ]},
        dataSource={"type": "Property", "value": "soilgrids"},
        uncertainty={"type": "Property", "value": 0.15},
        lastUpdated={"type": "Property", "value": "2026-05-11T00:00:00Z"},
    )
    assert entity.type == "AgriSoil"
    assert entity.dataSource.value == "soilgrids"


@pytest.mark.skip(reason="awaits T20 model migration — old AgriSoil pydantic shape removed")
def test_agri_soil_context():
    entity = AgriSoil(
        id="urn:ngsi-ld:AgriSoil:test-1",
        location={"type": "GeoProperty", "value": {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}},
        refAgriParcel={"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:parcel-1"},
        parcelVersionId={"type": "Property", "value": "v1"},
        horizons={"type": "Property", "value": []},
        dataSource={"type": "Property", "value": "soilgrids"},
        uncertainty={"type": "Property", "value": 0.15},
        lastUpdated={"type": "Property", "value": "2026-05-11T00:00:00Z"},
    )
    assert len(entity.context) == 1
