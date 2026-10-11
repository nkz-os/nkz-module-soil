from nkz_soil.util.ngsi import horizons_of


def test_normalized_list():
    e = {"horizons": {"type": "Property", "value": [{"depthFrom": 0}]}}
    assert horizons_of(e) == [{"depthFrom": 0}]


def test_single_element_unwrapped_by_orion():
    e = {"horizons": {"type": "Property", "value": {"depthFrom": 0, "ph": 7.1}}}
    assert horizons_of(e) == [{"depthFrom": 0, "ph": 7.1}]


def test_key_values_forms():
    assert horizons_of({"horizons": [{"depthFrom": 0}]}) == [{"depthFrom": 0}]
    assert horizons_of({"horizons": {"depthFrom": 0}}) == [{"depthFrom": 0}]


def test_missing_and_garbage():
    assert horizons_of({}) == []
    assert horizons_of({"horizons": {"type": "Property", "value": [1, {"a": 1}]}}) == [{"a": 1}]
