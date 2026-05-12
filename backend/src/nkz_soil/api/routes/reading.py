from fastapi import APIRouter, Depends, Query, HTTPException
from nkz_soil.api.dependencies import get_tenant_id
from nkz_soil.storage.orion import OrionClient

router = APIRouter()


@router.get("/parcel/{parcel_id}/summary")
async def parcel_summary(parcel_id: str, tenant_id: str = Depends(get_tenant_id)):
    async with OrionClient(tenant_id) as orion:
        entities = await orion.query_entities(type="AgriSoil")
        matching = [e for e in entities
                    if e.get("refAgriParcel", {}).get("object", "").endswith(parcel_id)]
        if not matching:
            raise HTTPException(status_code=404, detail="No AgriSoil found for this parcel")
        return matching[0]


@router.get("/parcel/{parcel_id}/horizons")
async def parcel_horizons(parcel_id: str, depth: str = "0-30", tenant_id: str = Depends(get_tenant_id)):
    depth_from, depth_to = map(int, depth.split("-"))
    async with OrionClient(tenant_id) as orion:
        entities = await orion.query_entities(type="AgriSoil")
        matching = [e for e in entities
                    if e.get("refAgriParcel", {}).get("object", "").endswith(parcel_id)]
        if not matching:
            raise HTTPException(status_code=404, detail="No AgriSoil found")
        horizons = matching[0].get("horizons", {}).get("value", [])
        filtered = [h for h in horizons if h["depthFrom"] >= depth_from and h["depthTo"] <= depth_to]
        return {"horizons": filtered}


@router.get("/parcel/{parcel_id}/raster")
async def parcel_raster(parcel_id: str, property: str, depth: str = "0-30", tenant_id: str = Depends(get_tenant_id)):
    async with OrionClient(tenant_id) as orion:
        entities = await orion.query_entities(type="SoilDerivedRaster")
        depth_from, depth_to = map(int, depth.split("-"))
        matching = [e for e in entities
                    if (e.get("refAgriParcel", {}).get("object", "").endswith(parcel_id)
                        and e.get("property", {}).get("value") == property
                        and e.get("depthFrom", {}).get("value") == depth_from
                        and e.get("depthTo", {}).get("value") == depth_to)]
        if not matching:
            raise HTTPException(status_code=404, detail="No raster found")
        from nkz_soil.storage.minio import get_minio_client, generate_presigned_url
        s3 = get_minio_client()
        raster = matching[0]
        uri = raster.get("storageUri", {}).get("value", "")
        bucket, key = uri.replace("s3://", "").split("/", 1)
        url = generate_presigned_url(s3, bucket, key)
        return {"url": url, "metadata": raster}


@router.get("/parcel/{parcel_id}/hydrologic-group")
async def parcel_hydrologic_group(parcel_id: str, tenant_id: str = Depends(get_tenant_id)):
    async with OrionClient(tenant_id) as orion:
        entities = await orion.query_entities(type="AgriSoil")
        matching = [e for e in entities
                    if e.get("refAgriParcel", {}).get("object", "").endswith(parcel_id)]
        if not matching:
            raise HTTPException(status_code=404, detail="No AgriSoil found")
        horizons = matching[0].get("horizons", {}).get("value", [])
        if not horizons:
            raise HTTPException(status_code=404, detail="No horizons found")
        group = horizons[0].get("hydrologicGroup", "B")
        return {"parcelId": parcel_id, "hydrologicGroup": group}


@router.get("/point")
async def point_query(lat: float, lon: float, depth: str = "0-30", tenant_id: str = Depends(get_tenant_id)):
    depth_from, depth_to = map(int, depth.split("-"))
    geometry = {"type": "Point", "coordinates": [lon, lat]}
    async with OrionClient(tenant_id) as orion:
        entities = await orion.query_entities(type="AgriSoil", geometry=geometry)
        if not entities:
            raise HTTPException(status_code=404, detail="No soil data at this point")
        horizons = entities[0].get("horizons", {}).get("value", [])
        filtered = [h for h in horizons if h["depthFrom"] >= depth_from and h["depthTo"] <= depth_to]
        return {"horizons": filtered, "source": entities[0].get("dataSource", {}).get("value")}


@router.get("/tenant/quota")
async def tenant_quota(tenant_id: str = Depends(get_tenant_id)):
    return {"tenantId": tenant_id, "evaluatedHectares": 0, "contractedHectares": 0}
