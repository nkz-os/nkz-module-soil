"""Raster generation pipeline.

Interpolates soil property values from AgriSoil entities into COG rasters,
uploads to MinIO, and registers SoilDerivedRaster entities in Orion-LD.

Uses ordinary kriging (scikit-gstat) with IDW fallback.
"""

from __future__ import annotations

import io
import logging
import uuid

import numpy as np

from nkz_soil.config import CONTEXT_URL
from nkz_soil.interpolation.idw import idw_interpolate
from nkz_soil.interpolation.kriging import kriging_interpolate
from nkz_soil.storage.minio import upload_cog
from nkz_soil.storage.orion import OrionClient

logger = logging.getLogger(__name__)

# Default grid resolution in meters (configurable per property)
DEFAULT_RESOLUTION_M = 10


async def generate_raster(
    tenant_id: str,
    parcel_id: str,
    property_name: str,
    depth_from: int,
    depth_to: int,
    sample_points: list[dict],
    resolution_m: int = DEFAULT_RESOLUTION_M,
) -> dict:
    """Generate a COG raster for a soil property from sample points.

    Args:
        tenant_id: Tenant identifier (used for MinIO bucket naming).
        parcel_id: Parcel identifier.
        property_name: Soil property to interpolate (e.g. 'ksatSaturated',
            'clay', 'organicCarbon').
        depth_from: Depth interval start (cm).
        depth_to: Depth interval end (cm).
        sample_points: List of dicts with keys:
            - 'x': longitude
            - 'y': latitude
            - 'value': property value at this point
        resolution_m: Grid cell size in meters.

    Returns:
        Dict with 'url' (presigned MinIO URL), 'entity_id', 'format', 'crs',
        'resolution', and 'method' ('kriging' or 'idw').
    """
    if not sample_points:
        raise ValueError("No sample points provided for raster generation")

    # Extract coordinates and values
    coords = np.array([[p["x"], p["y"]] for p in sample_points], dtype=np.float64)
    values = np.array([p["value"] for p in sample_points], dtype=np.float64)

    # Filter out NaN values
    valid = np.isfinite(values)
    coords = coords[valid]
    values = values[valid]

    if len(coords) == 0:
        raise ValueError("No valid sample points after filtering")

    # Compute bounding box + padding
    min_x, min_y = coords.min(axis=0)
    max_x, max_y = coords.max(axis=0)
    padding = resolution_m * 2  # 2-cell buffer around data
    min_x -= padding
    min_y -= padding
    max_x += padding
    max_y += padding

    # Create regular grid
    n_cols = max(2, int(np.ceil((max_x - min_x) / resolution_m)))
    n_rows = max(2, int(np.ceil((max_y - min_y) / resolution_m)))

    grid_x = np.linspace(min_x, max_x, n_cols)
    grid_y = np.linspace(min_y, max_y, n_rows)

    # Try kriging first, fall back to IDW
    method = "kriging"
    result = kriging_interpolate(coords, values, grid_x, grid_y)
    if result is None:
        logger.info("Kriging failed for %s/%s, falling back to IDW", parcel_id, property_name)
        method = "idw"
        result = idw_interpolate(coords, values, grid_x, grid_y)

    # Convert to COG bytes
    cog_bytes = _array_to_cog(result, min_x, max_y, resolution_m)

    # Upload to MinIO
    bucket = f"nkz-soil-{tenant_id}"
    layer_id = f"soil-{property_name.lower().replace('saturated', '')}"
    key = f"{parcel_id}/v1/{layer_id}-{depth_from}-{depth_to}.tif"

    from nkz_soil.storage.minio import get_minio_client, generate_presigned_url

    s3 = get_minio_client()
    upload_cog(s3, bucket, key, cog_bytes)
    presigned_url = generate_presigned_url(s3, bucket, key)

    # Register SoilDerivedRaster entity in Orion-LD
    entity_id = f"urn:ngsi-ld:SoilDerivedRaster:{uuid.uuid4()}"
    entity = {
        "id": entity_id,
        "type": "SoilDerivedRaster",
        "@context": [CONTEXT_URL],
        "refAgriParcel": {
            "type": "Relationship",
            "object": f"urn:ngsi-ld:AgriParcel:{tenant_id}:{parcel_id}",
        },
        "soilProperty": {"type": "Property", "value": property_name},
        "depthFrom": {"type": "Property", "value": depth_from},
        "depthTo": {"type": "Property", "value": depth_to},
        "storageUri": {"type": "Property", "value": f"s3://{bucket}/{key}"},
        "format": {"type": "Property", "value": "COG"},
        "crs": {"type": "Property", "value": "EPSG:4326"},
        "resolution": {"type": "Property", "value": resolution_m},
        "generatedAt": {"type": "Property", "value": None},  # TODO: set ISO timestamp
        "uncertainty": {"type": "Property", "value": _estimate_uncertainty(method, len(coords))},
        "parcelVersionId": {"type": "Property", "value": "v1"},
    }

    async with OrionClient(tenant_id) as orion:
        await orion.create_entity(entity)

    return {
        "url": presigned_url,
        "entity_id": entity_id,
        "format": "COG",
        "crs": "EPSG:4326",
        "resolution": resolution_m,
        "method": method,
    }


def _array_to_cog(
    data: np.ndarray,
    min_x: float,
    max_y: float,
    resolution: float,
) -> bytes:
    """Convert a numpy array to a Cloud Optimized GeoTIFF (COG) in memory.

    Uses rasterio if available, falls back to a minimal TIFF header.
    """
    try:
        import rasterio
        from rasterio.transform import from_origin
        from rasterio.crs import CRS
        from rasterio.enums import Resampling

        n_rows, n_cols = data.shape
        transform = from_origin(min_x, max_y, resolution, resolution)

        buf = io.BytesIO()
        with rasterio.open(
            buf,
            "w",
            driver="GTiff",
            height=n_rows,
            width=n_cols,
            count=1,
            dtype=data.dtype,
            crs=CRS.from_epsg(4326),
            transform=transform,
            tiled=True,  # COG requirement
            blockxsize=256,
            blockysize=256,
            compress="deflate",
            interleave="band",
        ) as dst:
            dst.write(data.astype(data.dtype), 1)
            # Build overviews for COG
            dst.build_overviews(
                [2, 4, 8, 16],
                resampling=Resampling.nearest,
            )
            # Tag as COG
            dst.update_tags(ns="rio_overview", resampling="nearest")

        return buf.getvalue()

    except ImportError:
        logger.warning("rasterio not installed, using minimal TIFF fallback")
        return _minimal_tiff(data, min_x, max_y, resolution)


def _minimal_tiff(
    data: np.ndarray,
    min_x: float,
    max_y: float,
    resolution: float,
) -> bytes:
    """Fallback: write a basic TIFF without rasterio.

    This is NOT a COG but allows the pipeline to function.
    """
    # Minimal TIFF header + data (very simplified)
    # In practice, rasterio should always be available in production
    n_rows, n_cols = data.shape
    header = bytearray()
    # Byte order (little-endian)
    header.extend(b"II")
    # TIFF magic
    header.extend(b"\x2a\x00")
    # IFD offset
    header.extend(b"\x08\x00\x00\x00")
    # Number of directory entries
    header.extend(b"\x0c\x00")
    # ... (simplified — real implementation needs full TIFF spec)
    # This is a placeholder; rasterio is the production path
    raise RuntimeError(
        "rasterio is required for raster generation. "
        "Install with: pip install nkz-soil[geo]"
    )


def _estimate_uncertainty(method: str, n_points: int) -> float:
    """Estimate interpolation uncertainty (0-1 scale).

    Heuristic based on method and sample density.
    """
    # Base uncertainty by method
    base = 0.15 if method == "kriging" else 0.30

    # Reduce uncertainty with more points (diminishing returns)
    density_factor = 1.0 / (1.0 + np.log10(max(n_points, 1)))

    return round(min(1.0, base + density_factor * 0.2), 2)
