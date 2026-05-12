from nkz_soil.pedotransfer.relative_compaction import relative_compaction, textural_class


def test_textural_class_loam():
    assert textural_class(sand=45, silt=35, clay=20) == "loam"


def test_textural_class_clay():
    assert textural_class(sand=20, silt=20, clay=60) == "clay"


def test_relative_compaction_normal():
    result = relative_compaction(bulk_density=1.32, sand=45, silt=35, clay=20)
    assert result["classification"] == "normal"
    assert 80 < result["value"] < 90


def test_relative_compaction_severe():
    result = relative_compaction(bulk_density=1.70, sand=80, silt=10, clay=10)
    assert result["classification"] == "severe"
