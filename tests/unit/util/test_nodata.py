from nkz_soil.util.nodata import is_soilgrids_nodata, sanitize_horizon


def test_is_soilgrids_nodata_sentinels():
    assert is_soilgrids_nodata(-3276.8)
    assert is_soilgrids_nodata(-9999)
    assert not is_soilgrids_nodata(6.5)
    assert not is_soilgrids_nodata(None)


def test_sanitize_horizon_drops_bad_ph():
    h = {"depthFrom": 0, "depthTo": 30, "ph": -3276.8, "sand": 42.0}
    out = sanitize_horizon(h)
    assert "ph" not in out
    assert out["sand"] == 42.0
