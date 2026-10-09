from nkz_soil.pedotransfer.porosity import bounded_saturation, total_porosity
from nkz_soil.pedotransfer.saxton_rawls import outside_calibration


def test_total_porosity_from_bulk_density():
    assert total_porosity(1.15) == 0.566
    assert total_porosity(1.325) == 0.5


def test_unusable_bulk_density_gives_no_porosity():
    assert total_porosity(None) is None
    assert total_porosity(0.0) is None
    assert total_porosity(115.0) is None      # g/cm3 x 100: a unit error
    assert total_porosity(-3276.8) is None    # nodata sentinel


def test_saturation_above_porosity_is_capped():
    # Live case: lab horizon, OC 6.09 %, bulk density 1.15 -> SR saturation 0.677.
    assert bounded_saturation(0.677, 1.15) == 0.566


def test_saturation_below_porosity_is_kept():
    assert bounded_saturation(0.45, 1.15) == 0.45


def test_no_density_keeps_saturation():
    assert bounded_saturation(0.677, None) == 0.677
    assert bounded_saturation(None, 1.15) is None


def test_calibration_range():
    assert outside_calibration(10, 6.09) is True     # OM 10.5 % > 8 %
    assert outside_calibration(65, 1.0) is True      # clay > 60 %
    assert outside_calibration(20, 1.0) is False
    assert outside_calibration(None, 1.0) is None
