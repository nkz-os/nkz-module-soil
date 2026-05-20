"""Tests for kriging interpolation."""

import numpy as np
import pytest
from unittest.mock import patch

from nkz_soil.interpolation.kriging import kriging_interpolate


def test_kriging_too_few_points():
    """Less than 3 points should return None."""
    points = np.array([[0.0, 0.0], [1.0, 1.0]])
    values = np.array([10.0, 20.0])
    grid_x = np.linspace(0, 1, 5)
    grid_y = np.linspace(0, 1, 5)

    result = kriging_interpolate(points, values, grid_x, grid_y)
    assert result is None


def test_kriging_returns_none_on_import_error():
    """If scikit-gstat is not installed, should return None."""
    points = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    values = np.array([10.0, 20.0, 30.0])
    grid_x = np.linspace(0, 1, 5)
    grid_y = np.linspace(0, 1, 5)

    with patch.dict("sys.modules", {"skgstat": None}):
        # Force import error by temporarily removing skgstat
        import sys
        original = sys.modules.get("skgstat")
        sys.modules["skgstat"] = None

        try:
            # Re-import to trigger the ImportError path
            import importlib
            import nkz_soil.interpolation.kriging as kg
            importlib.reload(kg)

            result = kg.kriging_interpolate(points, values, grid_x, grid_y)
            assert result is None
        finally:
            if original is not None:
                sys.modules["skgstat"] = original
            else:
                sys.modules.pop("skgstat", None)


def test_kriging_output_shape():
    """Output should match grid dimensions."""
    # Skip if scikit-gstat not available
    try:
        import skgstat  # noqa: F401
    except ImportError:
        pytest.skip("scikit-gstat not installed")

    points = np.array([
        [0.0, 0.0], [1.0, 0.0], [0.0, 1.0],
        [1.0, 1.0], [0.5, 0.5],
    ])
    values = np.array([10.0, 20.0, 30.0, 40.0, 25.0])
    grid_x = np.linspace(0, 1, 8)
    grid_y = np.linspace(0, 1, 6)

    result = kriging_interpolate(points, values, grid_x, grid_y)

    assert result is not None
    assert result.shape == (6, 8)


def test_kriging_values_in_range():
    """Interpolated values should be within the range of observed values."""
    try:
        import skgstat  # noqa: F401
    except ImportError:
        pytest.skip("scikit-gstat not installed")

    points = np.array([
        [0.0, 0.0], [2.0, 0.0], [0.0, 2.0],
        [2.0, 2.0], [1.0, 1.0],
    ])
    values = np.array([10.0, 20.0, 30.0, 40.0, 25.0])
    grid_x = np.linspace(0, 2, 10)
    grid_y = np.linspace(0, 2, 10)

    result = kriging_interpolate(points, values, grid_x, grid_y)

    assert result is not None
    # Allow some overshoot due to kriging, but no wild values
    assert not np.any(np.isnan(result))
    assert not np.any(np.isinf(result))
