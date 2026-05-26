from nkz_soil.workers.ingest import EnrichedHorizon, _apply_pedotransfer, _horizon_to_dict


def _h():
    return EnrichedHorizon(
        depth_from=0, depth_to=5, sand=40.0, silt=30.0, clay=30.0, organic_carbon=1.5,
        bulk_density=1.3, coarse_fragments=10.0,
        emit={"sand": None, "silt": None, "clay": None, "bulk_density": None,
              "coarse_fragments": None, "organic_carbon": 1.5},
        provenance={"clay": {"redistributable": False}},
    )


def test_restricted_raw_fractions_are_suppressed_but_derived_emitted():
    h = _apply_pedotransfer([_h()])[0]
    d = _horizon_to_dict(h)
    # raw JRC-only fractions withheld
    assert d["clay"] is None and d["sand"] is None and d["bulkDensity"] is None
    assert d["coarseFragments"] is None
    # open-source attribute still emitted
    assert d["organicCarbon"] == 1.5
    # derived products emitted (computed from winner values incl. restricted)
    assert d["availableWaterCapacity"] is not None
    assert d["fieldCapacity"] is not None and d["wiltingPoint"] is not None
    assert d["ksatSaturated"] is not None and d["hydrologicGroup"] in {"A", "B", "C", "D"}
