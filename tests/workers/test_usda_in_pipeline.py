from nkz_soil.workers.ingest import EnrichedHorizon, _apply_pedotransfer, _horizon_to_dict


def test_usda_class_computed_from_winner_fractions_even_when_suppressed():
    h = EnrichedHorizon(depth_from=0, depth_to=5, sand=42.0, silt=33.0, clay=25.0,
                        organic_carbon=1.5, emit={}, provenance={"clay": {"redistributable": False}})
    out = _horizon_to_dict(_apply_pedotransfer([h])[0])
    assert out["usdaTextureClass"] == "loam"   # derived & emitted even though raw clay is suppressed
    assert out["clay"] is None
