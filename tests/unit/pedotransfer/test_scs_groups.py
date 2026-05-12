from nkz_soil.pedotransfer.scs_groups import scs_hydrologic_group


def test_scs_group_a():
    assert scs_hydrologic_group(ksat=40) == "A"


def test_scs_group_b():
    assert scs_hydrologic_group(ksat=10) == "B"


def test_scs_group_c():
    assert scs_hydrologic_group(ksat=1) == "C"


def test_scs_group_d():
    assert scs_hydrologic_group(ksat=0.1) == "D"
