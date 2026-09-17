"""AgriSoilExtended must expose which provider won the ingest cascade,
so reading.py's `dataSource` field (already read, never populated) stops
always returning empty. Distinct from the LUCAS Texture Raster license
redaction of raw sand/silt/clay — dataSource must be present even when
those specific fields are legitimately withheld."""

from nkz_soil.models.domain import SoilDataResult
from nkz_soil.providers.base import ProviderResult
from nkz_soil.providers.lucas_texture_raster import LucasTextureRasterProvider
from nkz_soil.providers.soilgrids import SoilGridsProvider
from nkz_soil.workers.ingest import _legacy_results_to_provider_results, build_agri_soil_extended


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


def _legacy_result(provider_name: str, priority: int) -> SoilDataResult:
    """Mimic a legacy SoilDataResult exactly as `ingest_parcel` produces it: `.priority`
    already stamped from the provider's own `provider.priority` right after
    fetch/cache-read (see `ingest_parcel`'s `result.priority = provider.priority`)."""
    return SoilDataResult(
        provider=provider_name, horizons=[], uncertainty=0.2, geometry={},
        attribution="test", priority=priority,
    )


def test_legacy_priority_derivation_uses_real_priority_not_name_lookup():
    """Regression test: `_legacy_results_to_provider_results` (used by `ingest_parcel`
    to build the `results` passed into `build_agri_soil_extended`) used to re-derive
    priority from `PROVIDER_PRIORITIES.get(r.provider, 0)`. That dict's keys don't
    match every registered provider's real `.name` — `LucasTextureRasterProvider.name`
    is `"LUCAS-Texture"`, which has no entry, so it silently fell back to priority 0,
    below SoilGrids' 10, even though its real priority (22) should win. This test
    builds `SoilDataResult`s the way `ingest_parcel` actually does (provider name +
    already-stamped real priority) and calls the actual conversion function, so it
    would have caught the bug (unlike tests that hand-build `ProviderResult` objects
    directly, bypassing this derivation)."""
    lucas_tex = LucasTextureRasterProvider()
    soilgrids = SoilGridsProvider()
    assert lucas_tex.priority > soilgrids.priority  # sanity check on real config

    legacy_results = [
        _legacy_result(soilgrids.name, soilgrids.priority),
        _legacy_result(lucas_tex.name, lucas_tex.priority),
    ]

    provider_results = _legacy_results_to_provider_results(legacy_results)

    by_source = {r.source_tag: r.priority for r in provider_results}
    assert by_source[lucas_tex.name] == lucas_tex.priority, (
        "LUCAS-Texture must keep its real priority (22), not fall back to 0"
    )
    assert by_source[soilgrids.name] == soilgrids.priority

    winner = max(provider_results, key=lambda r: r.priority)
    assert winner.source_tag == lucas_tex.name, (
        "LUCAS-Texture (priority 22) must outrank SoilGrids (priority 10) in the cascade"
    )


def test_datasource_reports_lucas_texture_not_soilgrids_when_it_wins():
    """End-to-end regression for the same bug, through the field the previous task
    added: with the bug, a parcel where LUCAS-Texture Raster should win the cascade
    incorrectly reported `dataSource: "soilgrids"` instead of the correct winner."""
    lucas_tex = LucasTextureRasterProvider()
    soilgrids = SoilGridsProvider()

    legacy_results = [
        _legacy_result(soilgrids.name, soilgrids.priority),
        _legacy_result(lucas_tex.name, lucas_tex.priority),
    ]
    provider_results = _legacy_results_to_provider_results(legacy_results)

    entity = build_agri_soil_extended(
        parcel_id="urn:ngsi-ld:AgriParcel:p1",
        location={"type": "Point", "coordinates": [-2.0, 42.0]},
        merged_horizons=[{"depthFrom": 0, "depthTo": 5, "sand": 30.0}],
        results=provider_results,
        parcel_version="v1",
    )
    assert entity.dataSource == lucas_tex.name
