"""Tests for Available Water Capacity (AWC) pedotransfer function."""

from nkz_soil.pedotransfer.awc import awc_from_horizons


def test_awc_typical_values():
    """Typical FC > PWP should yield positive AWC."""
    awc = awc_from_horizons(field_capacity=0.30, wilting_point=0.15)
    assert awc == 0.15


def test_awc_zero():
    """FC == PWP should yield zero AWC."""
    awc = awc_from_horizons(field_capacity=0.20, wilting_point=0.20)
    assert awc == 0.0


def test_awc_negative_clamped():
    """PWP > FC (impossible) should return 0, not negative."""
    awc = awc_from_horizons(field_capacity=0.10, wilting_point=0.25)
    assert awc == 0.0


def test_awc_sandy_soil():
    """Sandy soil: low FC, low PWP, small AWC."""
    awc = awc_from_horizons(field_capacity=0.12, wilting_point=0.06)
    assert awc == 0.06


def test_awc_clay_soil():
    """Clay soil: high FC, high PWP, moderate AWC."""
    awc = awc_from_horizons(field_capacity=0.40, wilting_point=0.25)
    assert awc == 0.15
