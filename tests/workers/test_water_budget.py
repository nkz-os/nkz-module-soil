"""Tests for water_budget worker."""
from nkz_soil.workers.water_budget import (
    _compute_projection,
    _generate_recommendation,
    _default_forecast,
)


def test_compute_projection_basic():
    fc, pwp = 0.32, 0.14
    forecast = [{"day": "2026-06-16", "et0": 4.0, "precip": 0.0, "deficitAfter": 0}]
    result = _compute_projection(0.25, fc, pwp, forecast)
    assert len(result) == 1
    assert result[0]["deficitAfter"] > 0


def test_compute_projection_with_rain():
    fc, pwp = 0.32, 0.14
    forecast = [{"day": "2026-06-16", "et0": 2.0, "precip": 10.0, "deficitAfter": 0}]
    result = _compute_projection(0.20, fc, pwp, forecast)
    assert result[0]["deficitAfter"] < 12


def test_generate_recommendation_triggers_at_threshold():
    fc, awc = 0.32, 0.18
    depletion = 0.6
    # Simulate a computed forecast where deficit exceeds threshold (0.5 * 0.18 * 100 = 9.0)
    forecast = [
        {"day": "2026-06-16", "et0": 4.0, "precip": 0.0, "deficitAfter": 12.0},
        {"day": "2026-06-17", "et0": 4.0, "precip": 0.0, "deficitAfter": 15.5},
    ]
    reco = _generate_recommendation(depletion, forecast, fc, awc)
    assert reco is not None
    assert reco["shouldIrrigate"] is True
    assert reco["amountMm"] > 0


def test_generate_recommendation_below_threshold():
    fc, awc = 0.32, 0.18
    depletion = 0.3
    forecast = _default_forecast()
    reco = _generate_recommendation(depletion, forecast, fc, awc)
    assert reco is None
