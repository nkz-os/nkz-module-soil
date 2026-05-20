from fastapi import APIRouter, Depends, HTTPException

from nkz_soil.api.dependencies import get_tenant_id
from nkz_soil.api.limiter import limiter
from nkz_soil.storage.orion import OrionClient

router = APIRouter()


@router.get("/parcel/{parcel_id}/summary")
@limiter.exempt
async def parcel_summary(parcel_id: str, tenant_id: str = Depends(get_tenant_id)):
    async with OrionClient(tenant_id) as orion:
        entities = await orion.query_entities(type="AgriSoil")
        matching = [
            e
            for e in entities
            if e.get("refAgriParcel", {}).get("object", "").endswith(parcel_id)
        ]
        if not matching:
            raise HTTPException(
                status_code=404, detail="No AgriSoil found for this parcel"
            )
        return matching[0]


@router.get("/parcel/{parcel_id}/horizons")
@limiter.exempt
async def parcel_horizons(
    parcel_id: str, depth: str = "0-30", tenant_id: str = Depends(get_tenant_id)
):
    depth_from, depth_to = map(int, depth.split("-"))
    async with OrionClient(tenant_id) as orion:
        entities = await orion.query_entities(type="AgriSoil")
        matching = [
            e
            for e in entities
            if e.get("refAgriParcel", {}).get("object", "").endswith(parcel_id)
        ]
        if not matching:
            raise HTTPException(status_code=404, detail="No AgriSoil found")
        horizons = matching[0].get("horizons", {}).get("value", [])
        filtered = [
            h
            for h in horizons
            if h["depthFrom"] >= depth_from and h["depthTo"] <= depth_to
        ]
        return {"horizons": filtered}


@router.get("/parcel/{parcel_id}/raster")
@limiter.exempt
async def parcel_raster(
    parcel_id: str,
    property: str,
    depth: str = "0-30",
    tenant_id: str = Depends(get_tenant_id),
):
    async with OrionClient(tenant_id) as orion:
        entities = await orion.query_entities(type="SoilDerivedRaster")
        depth_from, depth_to = map(int, depth.split("-"))
        matching = [
            e
            for e in entities
            if (
                e.get("refAgriParcel", {}).get("object", "").endswith(parcel_id)
                and e.get("property", {}).get("value") == property
                and e.get("depthFrom", {}).get("value") == depth_from
                and e.get("depthTo", {}).get("value") == depth_to
            )
        ]
        if not matching:
            raise HTTPException(status_code=404, detail="No raster found")
        from nkz_soil.storage.minio import generate_presigned_url, get_minio_client

        s3 = get_minio_client()
        raster = matching[0]
        uri = raster.get("storageUri", {}).get("value", "")
        bucket, key = uri.replace("s3://", "").split("/", 1)
        url = generate_presigned_url(s3, bucket, key)
        return {"url": url, "metadata": raster}


@router.get("/parcel/{parcel_id}/hydrologic-group")
@limiter.exempt
async def parcel_hydrologic_group(
    parcel_id: str, tenant_id: str = Depends(get_tenant_id)
):
    async with OrionClient(tenant_id) as orion:
        entities = await orion.query_entities(type="AgriSoil")
        matching = [
            e
            for e in entities
            if e.get("refAgriParcel", {}).get("object", "").endswith(parcel_id)
        ]
        if not matching:
            raise HTTPException(status_code=404, detail="No AgriSoil found")
        horizons = matching[0].get("horizons", {}).get("value", [])
        if not horizons:
            raise HTTPException(status_code=404, detail="No horizons found")
        group = horizons[0].get("hydrologicGroup", "B")
        return {"parcelId": parcel_id, "hydrologicGroup": group}


@router.get("/point")
@limiter.exempt
async def point_query(
    lat: float, lon: float, depth: str = "0-30", tenant_id: str = Depends(get_tenant_id)
):
    depth_from, depth_to = map(int, depth.split("-"))
    geometry = {"type": "Point", "coordinates": [lon, lat]}
    async with OrionClient(tenant_id) as orion:
        entities = await orion.query_entities(type="AgriSoil", geometry=geometry)
        if not entities:
            raise HTTPException(status_code=404, detail="No soil data at this point")
        horizons = entities[0].get("horizons", {}).get("value", [])
        filtered = [
            h
            for h in horizons
            if h["depthFrom"] >= depth_from and h["depthTo"] <= depth_to
        ]
        return {
            "horizons": filtered,
            "source": entities[0].get("dataSource", {}).get("value"),
        }


@router.get("/tenant/quota")
@limiter.exempt
async def tenant_quota(tenant_id: str = Depends(get_tenant_id)):
    """Calculate evaluated hectares from AgriSoil entities in Orion-LD."""
    from shapely.geometry import shape
    from shapely.ops import transform
    import pyproj

    async with OrionClient(tenant_id) as orion:
        entities = await orion.query_entities(type="AgriSoil")

    total_area_m2 = 0.0
    for entity in entities:
        geometry = entity.get("location", {}).get("value")
        if not geometry:
            continue
        try:
            geom = shape(geometry)
            # Transform to area-preserving projection for accurate calculation
            geom_proj = transform(
                pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform,
                geom,
            )
            total_area_m2 += geom_proj.area
        except Exception:
            continue

    evaluated_ha = round(total_area_m2 / 10_000, 2)

    return {
        "tenantId": tenant_id,
        "evaluatedHectares": evaluated_ha,
        "contractedHectares": 0,  # TODO: configurable per tenant
        "soilEntities": len(entities),
    }
