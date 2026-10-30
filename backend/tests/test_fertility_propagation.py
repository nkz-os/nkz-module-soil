"""Lab fertility plumbing: Olsen conversion, provider averaging, horizon reads.

Contract: internal-docs-local/specs/2026-10-30-npk-and-penetrometer-contract.md
"""
import math

import pytest


# ── olsen_equivalent (Villalobos et al. 2020, Table 5) ────────────────────


def test_olsen_identity():
    from nkz_soil.models.fertility import olsen_equivalent

    assert olsen_equivalent(12.0, "olsen") == pytest.approx(12.0)


def test_olsen_bray1_conversion():
    from nkz_soil.models.fertility import olsen_equivalent

    assert olsen_equivalent(20.0, "bray1") == pytest.approx(20.0 * 0.47)


def test_olsen_unknown_method_raises():
    from nkz_soil.models.fertility import olsen_equivalent

    with pytest.raises(ValueError):
        olsen_equivalent(10.0, "egner_riehm")


def test_olsen_rejects_bad_values():
    from nkz_soil.models.fertility import olsen_equivalent

    for bad in (-1.0, True, "12", None):
        with pytest.raises(ValueError):
            olsen_equivalent(bad, "olsen")


# ── LabAnalysisProvider averaging ─────────────────────────────────────────


def _group(horizons, df=0, dt=30):
    from nkz_soil.providers.lab_analysis import _average_group

    return _average_group(df, dt, horizons)


def test_average_plain_mean_and_grouping():
    h = _group([
        {"depthFrom": 0, "depthTo": 30, "ph": 7.0, "nitrateN": 10.0},
        {"depthFrom": 0, "depthTo": 30, "ph": 8.0, "nitrateN": 20.0},
    ])
    assert h.ph == pytest.approx(7.5)
    assert h.nitrate_n == pytest.approx(15.0)


def test_average_p_normalizes_to_olsen_before_mean():
    # bray1 20 -> 9.4 olsen; olsen 10 -> 10; mean 9.7 (NOT the raw 15).
    h = _group([
        {"phosphorusAvailable": 20.0, "phosphorusMethod": "bray1"},
        {"phosphorusAvailable": 10.0, "phosphorusMethod": "olsen"},
    ])
    assert h.phosphorus_available == pytest.approx((20.0 * 0.47 + 10.0) / 2)
    assert h.phosphorus_method == "olsen"


def test_average_p_without_method_is_excluded():
    h = _group([
        {"phosphorusAvailable": 20.0, "phosphorusMethod": "olsen"},
        {"phosphorusAvailable": 99.0},  # no method: cannot convert, excluded
    ])
    assert h.phosphorus_available == pytest.approx(20.0)
    assert h.phosphorus_method == "olsen"


def test_average_k_most_frequent_method_only():
    # 2 ammonium_acetate vs 1 mehlich3: only the majority method is averaged.
    h = _group([
        {"potassiumExchangeable": 100.0, "potassiumMethod": "ammonium_acetate"},
        {"potassiumExchangeable": 200.0, "potassiumMethod": "ammonium_acetate"},
        {"potassiumExchangeable": 999.0, "potassiumMethod": "mehlich3"},
    ])
    assert h.potassium_exchangeable == pytest.approx(150.0)
    assert h.potassium_method == "ammonium_acetate"


def test_average_k_unmethoded_loses_tie_against_methoded():
    h = _group([
        {"potassiumExchangeable": 300.0},  # no method
        {"potassiumExchangeable": 100.0, "potassiumMethod": "ammonium_acetate"},
    ])
    assert h.potassium_exchangeable == pytest.approx(100.0)
    assert h.potassium_method == "ammonium_acetate"


def test_average_missing_everything_stays_none():
    h = _group([{"depthFrom": 0, "depthTo": 30}])
    assert h.ph is None
    assert h.phosphorus_available is None
    assert h.potassium_exchangeable is None


def test_average_handles_property_dicts():
    h = _group([
        {"ph": {"type": "Property", "value": 6.5}, "nitrateN": {"value": 5.0}},
    ])
    assert h.ph == pytest.approx(6.5)
    assert h.nitrate_n == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_fetch_groups_by_depth_interval():
    from nkz_soil.providers.lab_analysis import LabAnalysisProvider

    points = [
        {
            "id": "urn:ngsi-ld:SoilSamplingPoint:1",
            "horizons": {"type": "Property", "value": [
                {"depthFrom": 0, "depthTo": 30, "nitrateN": 10.0, "ph": 7.0},
            ]},
        },
        {   # Orion unwraps a single horizon to the object itself
            "id": "urn:ngsi-ld:SoilSamplingPoint:2",
            "horizons": {"depthFrom": 0, "depthTo": 30, "nitrateN": 20.0,
                         "ph": 8.0},
        },
        {
            "id": "urn:ngsi-ld:SoilSamplingPoint:3",
            "horizons": {"type": "Property", "value": [
                {"depthFrom": 30, "depthTo": 60, "nitrateN": 4.0},
            ]},
        },
    ]

    class _FakeOrion:
        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def query_entities(self, **_kw):
            return points

    from nkz_soil.providers import lab_analysis as la

    orig = la.OrionClient
    orig_tenant = la.current_tenant
    la.OrionClient = _FakeOrion
    la.current_tenant = lambda: "test_tenant"
    try:
        result = await LabAnalysisProvider().fetch({}, [], [])
    finally:
        la.OrionClient = orig
        la.current_tenant = orig_tenant

    assert len(result.horizons) == 2
    top = [h for h in result.horizons if h.depth_from == 0][0]
    sub = [h for h in result.horizons if h.depth_from == 30][0]
    assert top.nitrate_n == pytest.approx(15.0)
    assert top.ph == pytest.approx(7.5)
    assert sub.nitrate_n == pytest.approx(4.0)
    assert sub.ph is None


# ── /rasterize horizon lookup (_sampling_value) ───────────────────────────


def _sv(entity, prop, df=0, dt=30):
    from nkz_soil.api.routes.writing import _sampling_value

    return _sampling_value(entity, prop, df, dt)


def test_sampling_value_reads_overlapping_horizon():
    e = {"horizons": {"type": "Property", "value": [
        {"depthFrom": 0, "depthTo": 30, "penetrationResistance": 2.5},
        {"depthFrom": 30, "depthTo": 60, "penetrationResistance": 4.5},
    ]}}
    assert _sv(e, "penetrationResistance", 30, 60) == pytest.approx(4.5)
    assert _sv(e, "penetrationResistance", 0, 30) == pytest.approx(2.5)


def test_sampling_value_single_horizon_used_when_no_overlap():
    e = {"horizons": {"depthFrom": 0, "depthTo": 25, "ph": 7.2}}
    assert _sv(e, "ph", 0, 30) == pytest.approx(7.2)


def test_sampling_value_root_fallback_for_legacy_entities():
    e = {"penetrationResistance": {"type": "Property", "value": 3.1}}
    assert _sv(e, "penetrationResistance") == pytest.approx(3.1)


def test_sampling_value_missing_returns_none():
    e = {"horizons": {"type": "Property", "value": [
        {"depthFrom": 0, "depthTo": 30, "ph": 7.0},
    ]}}
    assert _sv(e, "penetrationResistance") is None


# ── ingest emission of fertility fields ───────────────────────────────────


def test_horizon_to_dict_emits_fertility():
    from nkz_soil.workers.ingest import EnrichedHorizon, _horizon_to_dict

    h = EnrichedHorizon(
        depth_from=0, depth_to=30,
        phosphorus_available=9.7, phosphorus_method="olsen",
        potassium_exchangeable=150.0, potassium_method="ammonium_acetate",
        nitrate_n=15.0, organic_matter=2.1,
    )
    d = _horizon_to_dict(h)
    assert d["phosphorusAvailable"] == pytest.approx(9.7)
    assert d["phosphorusMethod"] == "olsen"
    assert d["potassiumExchangeable"] == pytest.approx(150.0)
    assert d["potassiumMethod"] == "ammonium_acetate"
    assert d["nitrateN"] == pytest.approx(15.0)
    assert d["organicMatter"] == pytest.approx(2.1)


def test_cascade_merge_carries_fertility_from_lab_result():
    from nkz_soil.models.domain import DepthInterval, Horizon, SoilDataResult
    from nkz_soil.workers.ingest import _cascade_merge

    lab = SoilDataResult(
        provider="lab_analysis", horizons=[
            Horizon(depth_from=0, depth_to=30, sand=40.0,
                    phosphorus_available=9.7, phosphorus_method="olsen"),
        ], uncertainty=0.02, geometry={},
    )
    soilgrids = SoilDataResult(
        provider="soilgrids", horizons=[
            Horizon(depth_from=0, depth_to=30, sand=33.0),
        ], uncertainty=0.5, geometry={},
    )
    lab.priority = 100
    soilgrids.priority = 10
    merged = _cascade_merge([soilgrids, lab], [DepthInterval(depth_from=0, depth_to=30)])
    assert len(merged) == 1
    h = merged[0]
    assert h.sand == pytest.approx(40.0)  # lab wins over soilgrids
    assert h.phosphorus_available == pytest.approx(9.7)
    assert h.phosphorus_method == "olsen"
