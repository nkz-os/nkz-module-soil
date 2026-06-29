"""
Water Budget API — read-only endpoint for parcel water budget data.
Returns computed water budget from AgriSoil entity attributes + timeseries.
No computation happens on read — all data is pre-computed by the Arq worker.
"""
from fastapi import APIRouter, HTTPException

from nkz_platform_sdk import AuthContext
from nkz_soil.api.dependencies import require_auth
from nkz_soil.api.limiter import limiter
from nkz_soil.storage.orion import OrionClient, fetch_parcel_smi, parcel_ref_query

router = APIRouter()


@router.get("/parcel/{parcel_id}/water-budget")
@limiter.exempt
async def parcel_water_budget(parcel_id: str, auth: AuthContext = require_auth()):
    """Return the water budget for a parcel."""
    async with OrionClient(auth.tenant_id) as orion:
        entities = await orion.query_entities(
            type="AgriSoilExtended",
            q=parcel_ref_query(parcel_id),
            limit=1,
        )
        if not entities:
            raise HTTPException(status_code=404, detail="No AgriSoil found for this parcel")

        entity = entities[0]
        attrs = entity.get("attrs", entity)

        fc = _get_value(attrs, "fieldCapacity")
        pwp = _get_value(attrs, "wiltingPoint")
        awc = _get_value(attrs, "awc")
        moisture = _get_value(attrs, "currentMoisture")
        deficit = _get_value(attrs, "deficitMm")
        forecast_raw = _get_value(attrs, "forecast7d")
        last = _get_value(attrs, "lastComputed")

        awc_remaining_pct = (
            round(((moisture - pwp) / (fc - pwp) * 100), 1)
            if fc and pwp and (fc - pwp) > 0
            else 0
        ) if moisture is not None else None

        depletion = (
            (fc - moisture) / (fc - pwp)
            if fc and pwp and moisture is not None and (fc - pwp) > 0
            else 0
        )

        reco = None
        if depletion and depletion > 0.5 and awc:
            reco = {
                "shouldIrrigate": True,
                "amountMm": round((fc - moisture) * 100 * 0.6, 1) if fc and moisture else 0,
                "suggestedDay": forecast_raw[0]["day"] if forecast_raw else None,
                "reason": "Deficit supera umbral de agotamiento (50% AWC)",
            }
        elif depletion is not None:
            reco = {"shouldIrrigate": False}

        # TODO: query TimescaleDB for timeseries
        timeseries = []

        return {
            "parcelId": parcel_id,
            "fieldCapacity": fc,
            "wiltingPoint": pwp,
            "awc": awc,
            "currentMoisture": moisture,
            "awcRemainingPct": awc_remaining_pct,
            "deficitMm": deficit,
            "forecast": forecast_raw or [],
            "recommendation": reco,
            "lastComputed": last,
            "timeseries": timeseries,
        }


@router.get("/parcel/{parcel_id}/moisture")
@limiter.exempt
async def parcel_moisture(parcel_id: str, auth: AuthContext = require_auth()):
    """Return the latest SAR-derived Soil Moisture Index for a parcel.

    Queries ``EOProduct.sarMoisture`` (Sentinel-1 SAR, ESA Copernicus) from
    Orion-LD.  Returns ``available: false`` when no satellite data exists for
    the parcel instead of raising a 404, so callers can degrade gracefully.
    """
    result = await fetch_parcel_smi(parcel_id, auth.tenant_id)
    if result is None:
        return {
            "available": False,
            "smi": None,
            "sensingDate": None,
            "source": "Sentinel-1 SAR (ESA Copernicus)",
        }
    smi, sensing_date = result
    return {
        "available": True,
        "smi": round(smi, 4),
        "sensingDate": sensing_date or None,
        "source": "Sentinel-1 SAR (ESA Copernicus)",
    }


def _get_value(entity: dict, key: str, default=None):
    attr = entity.get(key, {})
    if isinstance(attr, dict):
        return attr.get("value", attr.get("object", default))
    return attr
