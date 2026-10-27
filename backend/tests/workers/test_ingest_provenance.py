"""Provenance must ignore provider results that contributed nothing."""

from nkz_soil.models.domain import Horizon, SoilDataResult
from nkz_soil.workers.ingest import (
    _highest_priority_source,
    _legacy_results_to_provider_results,
    _primary_source,
    build_agri_soil_extended,
)


def _res(provider: str, priority: int, with_horizon: bool) -> SoilDataResult:
    horizons = [Horizon(depth_from=0, depth_to=5, sand=30.0)] if with_horizon else []
    return SoilDataResult(
        provider=provider, horizons=horizons, uncertainty=0.2, geometry={},
        attribution="test", priority=priority,
    )


def _build(results):
    return build_agri_soil_extended(
        parcel_id="urn:ngsi-ld:AgriParcel:p1",
        location={"type": "Point", "coordinates": [-2.0, 42.0]},
        merged_horizons=[],
        results=_legacy_results_to_provider_results(results),
        parcel_version="v1",
    )


def test_empty_high_priority_result_does_not_win():
    results = [_res("lab_analysis", 100, False), _res("idena", 40, True)]
    assert _primary_source(results) == "idena"
    assert _highest_priority_source(_legacy_results_to_provider_results(results)) == "idena"
    assert _build(results).horizons.provided_by == "idena"
    assert _build(results).dataSource == "idena"


def test_lab_with_horizons_still_wins():
    results = [_res("lab_analysis", 100, True), _res("idena", 40, True)]
    assert _primary_source(results) == "lab_analysis"
    entity = _build(results)
    assert entity.horizons.provided_by == "lab_analysis"
    assert entity.dataSource == "lab_analysis"


def test_all_empty_gives_none_and_default():
    results = [_res("lab_analysis", 100, False), _res("idena", 40, False)]
    assert _highest_priority_source(_legacy_results_to_provider_results(results)) is None
    assert _primary_source(results) == "soilgrids"
