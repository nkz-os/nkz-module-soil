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


def test_saxton_rawls_ksat_nonzero_for_fine_textures():
    """Regression: the pre-fix Ksat formula returned 0.0 for every non-sandy
    texture (theta_s33 - theta_33 is negative there), which forced SCS
    hydrologic group D across the board."""
    for sand, clay in [(40, 20), (20, 15), (32, 34), (20, 55)]:
        result = saxton_rawls_2006(sand=sand, clay=clay, organic_carbon=1.0)
        assert result["ksat"] > 0.0, f"ksat=0 for sand={sand} clay={clay}"


def test_saxton_rawls_ksat_reference_ranges():
    """Ksat in the ballpark of Saxton & Rawls 2006 Table 3 (mm/h)."""
    cases = [
        (88, 5, 50.0, 200.0),  # sand ≈ 108
        (40, 20, 3.0, 20.0),  # loam ≈ 13
        (20, 15, 2.0, 15.0),  # silt loam ≈ 7
        (20, 55, 0.1, 3.0),  # clay ≈ 1.5
    ]
    for sand, clay, lo, hi in cases:
        ksat = saxton_rawls_2006(sand=sand, clay=clay, organic_carbon=1.0)["ksat"]
        assert lo <= ksat <= hi, f"sand={sand} clay={clay}: ksat={ksat}"


def test_saxton_rawls_ksat_ordering_sand_gt_loam_gt_clay():
    sand = saxton_rawls_2006(sand=88, clay=5, organic_carbon=1.0)["ksat"]
    loam = saxton_rawls_2006(sand=40, clay=20, organic_carbon=1.0)["ksat"]
    clay = saxton_rawls_2006(sand=20, clay=55, organic_carbon=1.0)["ksat"]
    assert sand > loam > clay
