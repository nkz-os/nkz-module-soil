from nkz_soil.pedotransfer.workability import METHOD_VERSION, WORKABILITY_METHOD, tillage_limits


def test_wet_limit_is_saturation_minus_ten_percent_air():
    assert tillage_limits(0.45, 0.13) == (0.35, 0.13)


def test_limits_are_rounded_to_three_decimals():
    assert tillage_limits(0.4567, 0.12345) == (0.357, 0.123)


def test_missing_input_gives_no_limits():
    assert tillage_limits(None, 0.13) == (None, None)
    assert tillage_limits(0.45, None) == (None, None)


def test_no_workable_range_gives_no_limits():
    # saturation - 0.10 at or below the wilting point: no inverted pair.
    assert tillage_limits(0.40, 0.30) == (None, None)
    assert tillage_limits(0.35, 0.30) == (None, None)


def test_method_names_its_sources():
    assert WORKABILITY_METHOD["version"] == METHOD_VERSION
    assert "Obour" in WORKABILITY_METHOD["wet"]
    assert "wilting point" in WORKABILITY_METHOD["dry"]
