from fastapi import APIRouter

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
async def layers_manifest():
    return MANIFEST


@router.get("/layers/{layer_id}/render")
async def render_layer(layer_id: str, parcel_id: str, depth: str = "0-30"):
    from nkz_soil.storage.minio import get_minio_client, generate_presigned_url
    s3 = get_minio_client()
    key = f"{parcel_id}/v1/{layer_id}-{depth}.tif"
    url = generate_presigned_url(s3, "nkz-soil", key)
    return {"url": url, "layerId": layer_id, "parcelId": parcel_id, "depth": depth}
