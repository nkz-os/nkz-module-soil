from nkz_soil.pedotransfer.saxton_rawls import saxton_rawls_2006


def test_saxton_rawls_ksat_sandy_loam():
    """Sandy loam: produces physically realistic ksat, fc > pwp."""
    result = saxton_rawls_2006(sand=60, clay=10, organic_carbon=2.0)
    assert result["ksat"] > 0
    assert result["ksat"] < 100
    assert result["field_capacity"] > result["wilting_point"]


def test_saxton_rawls_wilting_point_positive():
    result = saxton_rawls_2006(sand=10, clay=80, organic_carbon=1)
    assert result["wilting_point"] > 0
