from nkz_soil.models.domain import SoilDataResult, Horizon, DepthInterval
from nkz_soil.workers.ingest import _cascade_merge


def _r(provider, clay, redistributable, priority):
    return SoilDataResult(
        provider=provider, horizons=[Horizon(depth_from=0, depth_to=5, clay=clay)],
        uncertainty=0.2, geometry={}, license=provider, redistributable=redistributable,
        priority=priority,
    )


def test_winner_is_highest_priority_but_emit_is_best_redistributable():
    results = [_r("LUCAS-Texture", 30.0, False, 22), _r("soilgrids", 28.0, True, 10)]
    horizons = _cascade_merge(results, [DepthInterval(0, 5)])
    h = horizons[0]
    assert h.clay == 30.0                      # winner (for pedotransfer)
    assert h.emit["clay"] == 28.0              # best redistributable (for emission)
    assert h.provenance["clay"]["redistributable"] is False


def test_emit_none_when_only_source_is_restricted():
    horizons = _cascade_merge([_r("LUCAS-Texture", 30.0, False, 22)], [DepthInterval(0, 5)])
    h = horizons[0]
    assert h.clay == 30.0
    assert h.emit.get("clay") is None          # nothing redistributable supplied it
