import logging

from fastapi import APIRouter, HTTPException

from nkz_soil.api.limiter import limiter
from nkz_soil.storage.orion import OrionClient

logger = logging.getLogger(__name__)

# Map layer IDs to AgriSoil horizon property names
_LAYER_PROPERTY_MAP = {
    "soil-hydrologic-group": "hydrologicGroup",
    "soil-ksat": "ksatSaturated",
    "soil-clay": "clay",
    "soil-organic-carbon": "organicCarbon",
    "soil-ph": "ph",
    "soil-compaction": "relativeCompaction",
}

router = APIRouter()

MANIFEST = {
    "layers": [
        {
            "id": "soil-hydrologic-group",
            "label": "Hydrologic Group (SCS)",
            "category": "hydrology",
            "type": "categorical",
            "values": ["A", "B", "C", "D"],
            "colorRamp": ["#2c7bb6", "#abd9e9", "#fdae61", "#d7191c"],
            "unit": None,
            "depths": ["0-30", "30-60"],
        },
        {
            "id": "soil-ksat",
            "label": "Hydraulic Conductivity (Ksat)",
            "category": "hydrology",
            "type": "continuous",
            "range": [0, 50],
            "unit": "mm/h",
            "colorRamp": "viridis",
            "depths": ["0-5", "5-15", "15-30", "30-60", "60-100"],
        },
        {
            "id": "soil-clay",
            "label": "Clay Content",
            "category": "texture",
            "type": "continuous",
            "range": [0, 100],
            "unit": "%",
            "colorRamp": "YlOrBr",
            "depths": ["0-30", "30-60", "60-100"],
        },
        {
            "id": "soil-organic-carbon",
            "label": "Organic Carbon",
            "category": "carbon",
            "type": "continuous",
            "range": [0, 10],
            "unit": "%",
            "colorRamp": "BrBG",
            "depths": ["0-5", "5-15", "15-30", "30-60", "60-100"],
        },
        {
            "id": "soil-ph",
            "label": "Soil pH",
            "category": "chemistry",
            "type": "continuous",
            "range": [3, 10],
            "unit": "pH",
            "colorRamp": "Spectral",
            "depths": ["0-5", "5-15", "15-30", "30-60", "60-100"],
        },
        {
            "id": "soil-compaction",
            "label": "Relative Compaction",
            "category": "physical",
            "type": "categorical",
            "values": ["normal", "slight", "moderate", "severe"],
            "colorRamp": ["#1a9850", "#91cf60", "#fc8d59", "#d73027"],
            "unit": None,
            "depths": ["0-5", "5-15", "15-30", "30-60", "60-100"],
        },
    ]
}


@router.get("/layers/manifest")
@limiter.exempt
async def layers_manifest():
    return MANIFEST


@router.get("/layers/{layer_id}/render")
@limiter.exempt
async def render_layer(
    layer_id: str, parcel_id: str, depth: str = "0-30", tenant_id: str = None
):
    """Serve or generate a raster layer for a soil property.

    First checks if a SoilDerivedRaster entity already exists in Orion-LD.
    If found, returns a presigned MinIO URL. If not, generates the raster
    on-demand using kriging (with IDW fallback) from available AgriSoil data.
    """
    from nkz_soil.storage.minio import generate_presigned_url, get_minio_client

    depth_from, depth_to = map(int, depth.split("-"))

    # Step 1: Check if raster already exists in Orion
    async with OrionClient(tenant_id) as orion:
        rasters = await orion.query_entities(type="SoilDerivedRaster")
        matching = [
            r for r in rasters
            if (
                r.get("refAgriParcel", {}).get("object", "").endswith(parcel_id)
                and r.get("soilProperty", {}).get("value") == _LAYER_PROPERTY_MAP.get(layer_id, layer_id)
                and r.get("depthFrom", {}).get("value") == depth_from
                and r.get("depthTo", {}).get("value") == depth_to
            )
        ]
        if matching:
            raster = matching[0]
            uri = raster.get("storageUri", {}).get("value", "")
            if uri:
                s3 = get_minio_client()
                bucket, key = uri.replace("s3://", "").split("/", 1)
                url = generate_presigned_url(s3, bucket, key)
                return {
                    "url": url,
                    "layerId": layer_id,
                    "parcelId": parcel_id,
                    "depth": depth,
                    "generated": False,
                }

    # Step 2: Raster not found — generate on-demand
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required for raster generation")

    horizon_prop = _LAYER_PROPERTY_MAP.get(layer_id)
    if not horizon_prop:
        raise HTTPException(status_code=404, detail=f"Unknown layer: {layer_id}")

    # Collect sample points from all AgriSoil entities
    async with OrionClient(tenant_id) as orion:
        soils = await orion.query_entities(type="AgriSoilExtended")

    sample_points = []
    for soil in soils:
        horizons = soil.get("horizons", {}).get("value", [])
        location = soil.get("location", {}).get("value", {})
        if not location:
            continue

        # Use centroid of geometry as sample point
        centroid = _geometry_centroid(location)
        if centroid is None:
            continue

        for h in horizons:
            if h.get("depthFrom") == depth_from and h.get("depthTo") == depth_to:
                value = h.get(horizon_prop)
                if value is not None and isinstance(value, (int, float)):
                    sample_points.append({
                        "x": centroid[0],
                        "y": centroid[1],
                        "value": float(value),
                    })
                break

    if not sample_points:
        raise HTTPException(
            status_code=404,
            detail=f"No soil data available for {layer_id} at depth {depth}",
        )

    # Generate raster
    from nkz_soil.interpolation.raster import generate_raster

    result = await generate_raster(
        tenant_id=tenant_id,
        parcel_id=parcel_id,
        property_name=horizon_prop,
        depth_from=depth_from,
        depth_to=depth_to,
        sample_points=sample_points,
    )

    return {
        "url": result["url"],
        "layerId": layer_id,
        "parcelId": parcel_id,
        "depth": depth,
        "generated": True,
        "method": result["method"],
        "entityId": result["entity_id"],
    }


def _geometry_centroid(geometry: dict) -> tuple[float, float] | None:
    """Extract centroid from a GeoJSON geometry."""
    try:
        if geometry.get("type") == "Point":
            return tuple(geometry["coordinates"])
        if geometry.get("type") == "Polygon":
            coords = geometry["coordinates"][0]
            lon = sum(c[0] for c in coords) / len(coords)
            lat = sum(c[1] for c in coords) / len(coords)
            return (lon, lat)
    except (KeyError, IndexError, TypeError):
        pass
    return None
