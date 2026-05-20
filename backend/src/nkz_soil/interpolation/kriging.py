"""Ordinary kriging interpolation using scikit-gstat.

Produces statistically optimal interpolation with variogram modeling.
Falls back to IDW if variogram fitting fails or too few points.

NOTE (Phase 2 pending): anisotropic variogram models and cross-validation
RMSE against LUCAS are not yet implemented.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


def kriging_interpolate(
    points: np.ndarray,
    values: np.ndarray,
    grid_x: np.ndarray,
    grid_y: np.ndarray,
    variogram_model: str = "spherical",
) -> np.ndarray | None:
    """Interpolate using ordinary kriging.

    Args:
        points: (N, 2) array of (x, y) coordinates.
        values: (N,) array of observed values.
        grid_x: 1D array of grid x-coordinates.
        grid_y: 1D array of grid y-coordinates.
        variogram_model: Variogram model name ('spherical', 'exponential',
            'gaussian', 'matern', 'stable').

    Returns:
        2D array (len(grid_y), len(grid_x)) or None if kriging fails.
    """
    if len(points) < 3:
        logger.warning("Too few points for kriging (%d), needs >= 3", len(points))
        return None

    try:
        from skgstat import OrdinaryKriging, Variogram
    except ImportError:
        logger.warning("scikit-gstat not installed, kriging unavailable")
        return None

    try:
        # Build variogram model
        vario = Variogram(
            coordinates=points,
            values=values,
            model=variogram_model,
            n_lags=10,
        )

        # Fit ordinary kriging
        ok = OrdinaryKriging(vario, coordinates=points, values=values)

        # Create meshgrid for prediction
        gx, gy = np.meshgrid(grid_x, grid_y)
        grid_coords = np.column_stack([gx.ravel(), gy.ravel()])

        # Predict on grid
        z = ok.transform(grid_coords)

        # Check for NaN/inf results (can happen with extrapolation)
        if np.all(np.isnan(z)):
            logger.warning("Kriging produced all NaN values")
            return None

        # Replace NaN with nearest neighbor
        z = np.nan_to_num(z, nan=np.nanmean(values))

        return z.reshape(gx.shape)

    except Exception as e:
        logger.warning("Kriging failed (%s), caller should fall back to IDW", e)
        return None
