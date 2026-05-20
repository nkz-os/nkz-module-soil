"""Inverse Distance Weighting (IDW) interpolation.

Fallback method when kriging cannot converge (too few points,
collinear points, or variogram fitting failure).
"""

from __future__ import annotations

import numpy as np


def idw_interpolate(
    points: np.ndarray,
    values: np.ndarray,
    grid_x: np.ndarray,
    grid_y: np.ndarray,
    power: float = 2.0,
    max_points: int | None = None,
) -> np.ndarray:
    """Interpolate values on a regular grid using IDW.

    Args:
        points: (N, 2) array of (x, y) coordinates.
        values: (N,) array of observed values.
        grid_x: 1D array of grid x-coordinates.
        grid_y: 1D array of grid y-coordinates.
        power: Distance weighting exponent (default 2.0).
        max_points: If set, use only the N nearest points per grid cell.

    Returns:
        2D array (len(grid_y), len(grid_x)) of interpolated values.
    """
    if len(points) == 0:
        raise ValueError("No points provided for interpolation")
    if len(points) == 1:
        # Single point: fill entire grid with that value
        return np.full((len(grid_y), len(grid_x)), values[0])

    gx, gy = np.meshgrid(grid_x, grid_y)
    grid_shape = gx.shape
    n_cells = grid_shape[0] * grid_shape[1]

    # Flatten grid for vectorized computation
    grid_coords = np.column_stack([gx.ravel(), gy.ravel()])  # (n_cells, 2)

    if max_points is not None and max_points < len(points):
        # For each grid cell, find nearest max_points and interpolate
        result = np.empty(n_cells, dtype=np.float64)
        for i in range(n_cells):
            dists = np.sqrt(((points - grid_coords[i]) ** 2).sum(axis=1))
            idx = np.argpartition(dists, max_points)[:max_points]
            near_dists = dists[idx]
            near_vals = values[idx]
            result[i] = _idw_weighted(near_vals, near_dists, power)
    else:
        # Full distance matrix (memory-intensive for large grids)
        # dists: (n_cells, n_points)
        dists = np.sqrt(
            ((grid_coords[:, np.newaxis, :] - points[np.newaxis, :, :]) ** 2).sum(axis=2)
        )
        result = _idw_weighted_batch(values, dists, power)

    return result.reshape(grid_shape)


def _idw_weighted(values: np.ndarray, dists: np.ndarray, power: float) -> float:
    """IDW for a single location."""
    zero_mask = dists == 0
    if zero_mask.any():
        # Exact match — return that value directly
        return float(values[zero_mask][0])
    weights = 1.0 / np.power(dists, power)
    return float(np.sum(weights * values) / np.sum(weights))


def _idw_weighted_batch(
    values: np.ndarray, dists: np.ndarray, power: float
) -> np.ndarray:
    """Vectorized IDW for all grid cells at once."""
    # Avoid division by zero
    eps = 1e-10
    weights = 1.0 / np.power(dists + eps, power)
    # If any distance is truly zero (exact match), set weight to infinity
    # so that value dominates
    exact = dists < eps
    if exact.any():
        # For cells with exact matches, use the matched value directly
        weights[exact] = np.inf
    weighted_sum = np.sum(weights * values[np.newaxis, :], axis=1)
    total_weight = np.sum(weights, axis=1)
    # Handle exact matches
    has_exact = np.any(exact, axis=1)
    result = np.where(has_exact, 0.0, weighted_sum / total_weight)
    for i in np.where(has_exact)[0]:
        match_idx = np.where(exact[i])[0][0]
        result[i] = values[match_idx]
    return result
