from nkz_soil.pedotransfer.usda_texture import usda_texture_class


def test_known_classes():
    assert usda_texture_class(sand=42, silt=33, clay=25) == "loam"
    assert usda_texture_class(sand=55, silt=30, clay=15) == "sandy-loam"
    assert usda_texture_class(sand=38, silt=32, clay=30) == "clay-loam"
    assert usda_texture_class(sand=20, silt=10, clay=70) == "clay"
    assert usda_texture_class(sand=90, silt=5, clay=5) == "sand"
    assert usda_texture_class(sand=5, silt=90, clay=5) == "silt"


def test_returns_none_on_invalid_sum():
    assert usda_texture_class(sand=10, silt=10, clay=10) is None


def test_handles_none_inputs():
    assert usda_texture_class(sand=None, silt=33, clay=25) is None
