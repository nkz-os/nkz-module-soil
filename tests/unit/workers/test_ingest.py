from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nkz_soil.models.domain import Horizon, SoilDataResult
from nkz_soil.workers.ingest import (
    STANDARD_DEPTHS,
    EnrichedHorizon,
    _aggregate_uncertainty,
    _apply_pedotransfer,
    _cascade_merge,
    _horizon_to_dict,
    _primary_source,
)


def make_result(provider, horizons, uncertainty=0.1, priority=0):
    return SoilDataResult(
        provider=provider,
        horizons=horizons,
        uncertainty=uncertainty,
        geometry={},
        priority=priority,
    )


def test_cascade_merge_high_priority_wins():
    high = make_result("lab_analysis", [
        Horizon(depth_from=0, depth_to=5, sand=50, silt=30, clay=20, ph=6.5),
    ], priority=100)
    low = make_result("soilgrids", [
        Horizon(depth_from=0, depth_to=5, sand=40, silt=40, clay=20, ph=7.0),
    ], priority=10)

    merged = _cascade_merge([low, high], STANDARD_DEPTHS)
    h0 = next(h for h in merged if h.depth_from == 0 and h.depth_to == 5)

    assert h0.sand == 50
    assert h0.ph == 6.5


def test_cascade_merge_gap_filling():
    partial = make_result("lab_analysis", [
        Horizon(depth_from=0, depth_to=5, sand=50),
    ], priority=100)
    full = make_result("soilgrids", [
        Horizon(depth_from=0, depth_to=5, sand=40, silt=40, clay=20),
        Horizon(depth_from=5, depth_to=15, sand=35, silt=45, clay=20),
    ], priority=10)

    merged = _cascade_merge([full, partial], STANDARD_DEPTHS)
    h0 = next(h for h in merged if h.depth_from == 0 and h.depth_to == 5)
    h1 = next(h for h in merged if h.depth_from == 5 and h.depth_to == 15)

    assert h0.sand == 50
    assert h0.silt == 40
    assert h1.sand == 35


def test_apply_pedotransfer_ksat_and_hydrologic_group():
    horizons = [
        EnrichedHorizon(depth_from=0, depth_to=5, sand=60, clay=10, organic_carbon=2.0),
    ]
    result = _apply_pedotransfer(horizons)

    assert result[0].ksat_saturated is not None
    assert result[0].ksat_saturated > 0
    assert result[0].hydrologic_group in ("A", "B", "C", "D")
    assert result[0].available_water_capacity is not None
    assert result[0].available_water_capacity > 0


def test_apply_pedotransfer_relative_compaction():
    horizons = [
        EnrichedHorizon(
            depth_from=0, depth_to=5,
            sand=45, silt=35, clay=20,
            bulk_density=1.32,
        ),
    ]
    result = _apply_pedotransfer(horizons)

    assert result[0].relative_compaction is not None
    assert "value" in result[0].relative_compaction
    assert "classification" in result[0].relative_compaction


def test_aggregate_uncertainty():
    r1 = make_result("lab", [], uncertainty=0.02)
    r2 = make_result("soilgrids", [], uncertainty=0.25)
    assert _aggregate_uncertainty([r1, r2]) == 0.14


def test_aggregate_uncertainty_empty():
    assert _aggregate_uncertainty([]) == 0.5


def test_primary_source():
    r1 = make_result("soilgrids", [])
    r2 = make_result("lab_analysis", [])
    assert _primary_source([r1, r2]) == "lab_analysis"


def test_primary_source_empty():
    assert _primary_source([]) == "soilgrids"


def test_horizon_to_dict():
    h = EnrichedHorizon(
        depth_from=0, depth_to=5,
        sand=50, silt=30, clay=20,
        ksat_saturated=12.5,
        hydrologic_group="B",
    )
    d = _horizon_to_dict(h)
    assert d["depthFrom"] == 0
    assert d["depthTo"] == 5
    assert d["sand"] == 50
    assert d["ksatSaturated"] == 12.5
    assert d["hydrologicGroup"] == "B"


@pytest.mark.asyncio
async def test_ingest_parcel_creates_entity():
    from nkz_soil.workers.ingest import ingest_parcel

    mock_orion = AsyncMock()
    mock_orion.__aenter__ = AsyncMock(return_value=mock_orion)
    mock_orion.__aexit__ = AsyncMock(return_value=None)
    mock_orion.create_entity = AsyncMock()
    mock_orion.get_entity = AsyncMock(return_value=None)  # not found → create path

    mock_cb = AsyncMock()
    mock_cb.is_open = AsyncMock(return_value=False)
    mock_cb.record_success = AsyncMock()
    mock_cb.record_failure = AsyncMock()

    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    mock_cache.close = AsyncMock()

    with patch("nkz_soil.workers.ingest.OrionClient", return_value=mock_orion):
        ctx = {"registry": MagicMock(), "circuit_breaker": mock_cb, "cache": mock_cache}
        ctx["registry"].get_all.return_value = []

        result = await ingest_parcel(
            ctx,
            parcel_id="test-parcel",
            tenant_id="test-tenant",
            geometry={"type": "Point", "coordinates": [-1.6, 42.8]},
            parcel_version_id="v1",
        )

        assert result["status"] == "ingested"
        assert result["parcelId"] == "test-parcel"
        mock_orion.create_entity.assert_called_once()
        entity = mock_orion.create_entity.call_args[0][0]
        assert entity["type"] == "AgriSoilExtended"
        # No @context in the body — the SDK injects the reachable platform context.
        assert "@context" not in entity


@pytest.mark.asyncio
async def test_ingest_parcel_links_real_parcel_urn():
    """hasAgriParcel must point to the real parcel URN (no tenant prefix).

    The old code prefixed parcel_id with the tenant, yielding
    urn:ngsi-ld:AgriParcel:<tenant>:<uuid> — a non-existent entity that broke
    consumer joins (bioorch/crop-health) and the backfill idempotency check.
    """
    from nkz_soil.workers.ingest import ingest_parcel

    mock_orion = AsyncMock()
    mock_orion.__aenter__ = AsyncMock(return_value=mock_orion)
    mock_orion.__aexit__ = AsyncMock(return_value=None)
    mock_orion.create_entity = AsyncMock()
    mock_orion.get_entity = AsyncMock(return_value=None)  # not found → create path

    mock_cb = AsyncMock()
    mock_cb.is_open = AsyncMock(return_value=False)
    mock_cb.record_success = AsyncMock()
    mock_cb.record_failure = AsyncMock()

    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    mock_cache.close = AsyncMock()

    with patch("nkz_soil.workers.ingest.OrionClient", return_value=mock_orion):
        ctx = {"registry": MagicMock(), "circuit_breaker": mock_cb, "cache": mock_cache}
        ctx["registry"].get_all.return_value = []

        await ingest_parcel(
            ctx,
            parcel_id="da36ccd2-85d2-4c76-b552-c5c835a987c1",
            tenant_id="montiko",
            geometry={"type": "Point", "coordinates": [-1.6, 42.8]},
            parcel_version_id="v1",
        )

        entity = mock_orion.create_entity.call_args[0][0]
        assert entity["hasAgriParcel"]["object"] == (
            "urn:ngsi-ld:AgriParcel:da36ccd2-85d2-4c76-b552-c5c835a987c1"
        )
        assert entity["id"] == (
            "urn:ngsi-ld:AgriSoilExtended:da36ccd2-85d2-4c76-b552-c5c835a987c1"
        )


@pytest.mark.asyncio
async def test_ingest_parcel_updates_via_append_not_patch():
    """Re-ingesting an already-existing entity must use append_entity_attrs
    (POST /attrs), not patch_entity (PATCH /attrs).

    Bug (found 2026-07-23 during live verification): PATCH /attrs only
    updates attributes the entity already has — a field introduced after
    the entity was first created (e.g. dataSource) silently lands in
    Orion's `notUpdated` and never persists on re-ingest of an existing
    parcel. Only affects parcels ingested before a new field was added;
    a fresh create was never broken.
    """
    from nkz_soil.workers.ingest import ingest_parcel

    entity_id = "urn:ngsi-ld:AgriSoilExtended:test-parcel"
    mock_orion = AsyncMock()
    mock_orion.__aenter__ = AsyncMock(return_value=mock_orion)
    mock_orion.__aexit__ = AsyncMock(return_value=None)
    mock_orion.create_entity = AsyncMock()
    mock_orion.patch_entity = AsyncMock()
    mock_orion.append_entity_attrs = AsyncMock()
    mock_orion.get_entity = AsyncMock(return_value={"id": entity_id})  # entity exists → append path

    mock_cb = AsyncMock()
    mock_cb.is_open = AsyncMock(return_value=False)
    mock_cb.record_success = AsyncMock()
    mock_cb.record_failure = AsyncMock()

    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    mock_cache.close = AsyncMock()

    with patch("nkz_soil.workers.ingest.OrionClient", return_value=mock_orion):
        ctx = {"registry": MagicMock(), "circuit_breaker": mock_cb, "cache": mock_cache}
        ctx["registry"].get_all.return_value = []

        await ingest_parcel(
            ctx,
            parcel_id="test-parcel",
            tenant_id="test-tenant",
            geometry={"type": "Point", "coordinates": [-1.6, 42.8]},
            parcel_version_id="v1",
        )

        mock_orion.append_entity_attrs.assert_called_once()
        mock_orion.patch_entity.assert_not_called()
        mock_orion.create_entity.assert_not_called()
        called_id, called_attrs = mock_orion.append_entity_attrs.call_args[0]
        assert called_id == entity_id
        assert "id" not in called_attrs
        assert "type" not in called_attrs


def test_apply_pedotransfer_sets_tillage_limits():
    from nkz_soil.pedotransfer.saxton_rawls import saxton_rawls_2006

    h = _apply_pedotransfer([
        EnrichedHorizon(depth_from=0, depth_to=5, sand=40, clay=20, organic_carbon=1.0),
    ])[0]
    ptf = saxton_rawls_2006(40, 20, 1.0)
    assert h.wet_tillage_limit == round(ptf["saturation"] - 0.10, 3)
    assert h.dry_tillage_limit == round(ptf["wilting_point"], 3)


def test_apply_pedotransfer_without_texture_has_no_tillage_limits():
    h = _apply_pedotransfer([EnrichedHorizon(depth_from=0, depth_to=5)])[0]
    assert h.wet_tillage_limit is None and h.dry_tillage_limit is None


def test_horizon_to_dict_emits_tillage_limits_and_method():
    h = EnrichedHorizon(depth_from=0, depth_to=5, wet_tillage_limit=0.35, dry_tillage_limit=0.13)
    d = _horizon_to_dict(h)
    assert d["wetTillageLimit"] == 0.35
    assert d["dryTillageLimit"] == 0.13
    assert d["tillageLimitsMethod"] == "1"


def test_horizon_to_dict_without_limits_has_no_method():
    d = _horizon_to_dict(EnrichedHorizon(depth_from=0, depth_to=5))
    assert d["wetTillageLimit"] is None and d["dryTillageLimit"] is None
    assert d["tillageLimitsMethod"] is None


def test_rederive_horizons_adds_missing_limits():
    from nkz_soil.workers.ingest import _rederive_horizons

    old = [{"depthFrom": 0, "depthTo": 5, "saturation": 0.45, "wiltingPoint": 0.13},
           {"depthFrom": 5, "depthTo": 15}]
    new = _rederive_horizons(old)
    assert new[0]["wetTillageLimit"] == 0.35 and new[0]["dryTillageLimit"] == 0.13
    assert new[0]["tillageLimitsMethod"] == "1"
    assert new[1]["wetTillageLimit"] is None and new[1]["tillageLimitsMethod"] is None
    assert old[0].get("wetTillageLimit") is None  # input untouched


def test_rederive_horizons_returns_none_when_up_to_date():
    from nkz_soil.workers.ingest import _rederive_horizons

    current = [{"depthFrom": 0, "depthTo": 5, "saturation": 0.45, "wiltingPoint": 0.13,
                "wetTillageLimit": 0.35, "dryTillageLimit": 0.13, "tillageLimitsMethod": "1"}]
    assert _rederive_horizons(current) is None


def test_rederive_horizons_ignores_nodata_sentinels():
    from nkz_soil.workers.ingest import _rederive_horizons

    # A sentinel saturation yields no limits: nothing to write, no patch.
    assert _rederive_horizons([{"depthFrom": 0, "depthTo": 5, "saturation": -32768.0,
                                "wiltingPoint": 0.13}]) is None
    stale = _rederive_horizons([{"depthFrom": 0, "depthTo": 5, "saturation": -32768.0,
                                 "wiltingPoint": 0.13, "wetTillageLimit": 0.2}])
    assert stale[0]["wetTillageLimit"] is None


@pytest.mark.asyncio
async def test_rederive_tillage_limits_patches_only_changed_entities():
    from nkz_soil.workers.ingest import rederive_tillage_limits

    stale = {
        "id": "urn:ngsi-ld:AgriSoilExtended:a",
        "horizons": {"type": "Property", "providedBy": "soilgrids", "createdAt": "x",
                     "value": [{"depthFrom": 0, "depthTo": 5, "saturation": 0.45,
                                "wiltingPoint": 0.13}]},
    }
    fresh = {
        "id": "urn:ngsi-ld:AgriSoilExtended:b",
        "horizons": {"type": "Property", "value": [
            {"depthFrom": 0, "depthTo": 5, "saturation": 0.45, "wiltingPoint": 0.13,
             "wetTillageLimit": 0.35, "dryTillageLimit": 0.13, "tillageLimitsMethod": "1"}]},
    }
    orion = AsyncMock()
    orion.__aenter__ = AsyncMock(return_value=orion)
    orion.__aexit__ = AsyncMock(return_value=None)
    orion.query_entities = AsyncMock(return_value=[stale, fresh])
    orion.patch_entity = AsyncMock()

    with patch("nkz_soil.workers.ingest.OrionClient", return_value=orion), \
         patch("nkz_soil.workers.ingest._soil_tenants", AsyncMock(return_value=["t1"])):
        await rederive_tillage_limits({})

    orion.patch_entity.assert_called_once()
    entity_id, attrs = orion.patch_entity.call_args.args
    assert entity_id == "urn:ngsi-ld:AgriSoilExtended:a"
    sent = attrs["horizons"]
    assert sent["providedBy"] == "soilgrids"          # sub-properties preserved
    assert "createdAt" not in sent                     # system fields not sent back
    assert sent["value"][0]["wetTillageLimit"] == 0.35
