"""
Soil Moisture API — read-only endpoint for SAR-derived Soil Moisture Index.
"""
from fastapi import APIRouter
from nkz_platform_sdk import AuthContext

from nkz_soil.api.dependencies import require_auth
from nkz_soil.api.limiter import limiter
from nkz_soil.storage.orion import fetch_parcel_smi

router = APIRouter()
_REQUIRE_AUTH = require_auth()


@router.get("/parcel/{parcel_id}/moisture")
@limiter.exempt
async def parcel_moisture(parcel_id: str, auth: AuthContext = _REQUIRE_AUTH):
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
