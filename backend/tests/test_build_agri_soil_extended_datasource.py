"""AgriSoilExtended must expose which provider won the ingest cascade,
so reading.py's `dataSource` field (already read, never populated) stops
always returning empty. Distinct from the LUCAS Texture Raster license
redaction of raw sand/silt/clay — dataSource must be present even when
those specific fields are legitimately withheld."""

from nkz_soil.providers.base import ProviderResult
from nkz_soil.workers.ingest import build_agri_soil_extended


def _result(priority, source_tag, license_="open", **attrs):
    return ProviderResult(
        priority=priority,
        attributes=attrs,
        source_tag=source_tag,
        license=license_,
    )


def test_datasource_is_highest_priority_contributor():
    results = [
        _result(10, "soilgrids", sand=30.0, clay=20.0),
        _result(100, "lab_analysis", ph=6.5),
    ]
    entity = build_agri_soil_extended(
        parcel_id="urn:ngsi-ld:AgriParcel:p1",
        location={"type": "Point", "coordinates": [-2.0, 42.0]},
        merged_horizons=[{"depthFrom": 0, "depthTo": 5, "ph": 6.5, "sand": 30.0}],
        results=results,
        parcel_version="v1",
    )
    assert entity.dataSource == "lab_analysis"


def test_datasource_present_even_when_texture_withheld():
    """LUCAS Texture Raster wins but its raw fractions are withheld by
    license — dataSource must still say so, not silently disappear."""
    results = [
        _result(22, "lucas_texture_raster", sand=None, clay=None, organic_carbon=1.8),
    ]
    entity = build_agri_soil_extended(
        parcel_id="urn:ngsi-ld:AgriParcel:p1",
        location={"type": "Point", "coordinates": [-2.0, 42.0]},
        merged_horizons=[{"depthFrom": 0, "depthTo": 5, "organicCarbon": 1.8, "sand": None}],
        results=results,
        parcel_version="v1",
    )
    assert entity.dataSource == "lucas_texture_raster"


def test_datasource_none_when_no_results():
    entity = build_agri_soil_extended(
        parcel_id="urn:ngsi-ld:AgriParcel:p1",
        location={"type": "Point", "coordinates": [-2.0, 42.0]},
        merged_horizons=[],
        results=[],
        parcel_version="v1",
    )
    assert entity.dataSource is None
    assert "dataSource" not in entity.to_ngsi()
