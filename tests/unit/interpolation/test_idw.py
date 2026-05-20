"""Tests for IDW interpolation."""

import numpy as np
import pytest

from nkz_soil.interpolation.idw import idw_interpolate


def test_idw_single_point():
    """Single point should fill entire grid with that value."""
    points = np.array([[0.0, 0.0]])
    values = np.array([42.0])
    grid_x = np.linspace(-1, 1, 5)
    grid_y = np.linspace(-1, 1, 5)

    result = idw_interpolate(points, values, grid_x, grid_y)

    assert result.shape == (5, 5)
    assert np.allclose(result, 42.0)


def test_idw_two_points():
    """Two points: midpoint should be average (power=2)."""
    points = np.array([[0.0, 0.0], [2.0, 0.0]])
    values = np.array([0.0, 100.0])
    grid_x = np.array([0.0, 1.0, 2.0])
    grid_y = np.array([0.0])

    result = idw_interpolate(points, values, grid_x, grid_y)

    # At x=0: value=0 (exact match)
    assert result[0, 0] == 0.0
    # At x=2: value=100 (exact match)
    assert result[0, 2] == 100.0
    # At x=1: equidistant, should be ~50
    assert abs(result[0, 1] - 50.0) < 0.1


def test_idw_empty_points_raises():
    """No points should raise ValueError."""
    points = np.array([]).reshape(0, 2)
    values = np.array([])
    grid_x = np.linspace(0, 1, 3)
    grid_y = np.linspace(0, 1, 3)

    with pytest.raises(ValueError, match="No points"):
        idw_interpolate(points, values, grid_x, grid_y)


def test_idw_max_points():
    """With max_points, only nearest N points are used."""
    # 5 points in a line
    points = np.array([[i, 0.0] for i in range(5)])
    values = np.array([float(i * 10) for i in range(5)])
    grid_x = np.array([2.5])
    grid_y = np.array([0.0])

    result = idw_interpolate(points, values, grid_x, grid_y, max_points=2)

    # Should use only 2 nearest points (at x=2 and x=3)
    assert result.shape == (1, 1)
    # Value should be weighted average of 20 and 30
    assert 20.0 < result[0, 0] < 30.0


def test_idw_grid_shape():
    """Output grid should match input grid dimensions."""
    points = np.array([[0.0, 0.0], [1.0, 1.0]])
    values = np.array([10.0, 20.0])
    grid_x = np.linspace(0, 1, 10)
    grid_y = np.linspace(0, 1, 8)

    result = idw_interpolate(points, values, grid_x, grid_y)

    assert result.shape == (8, 10)
