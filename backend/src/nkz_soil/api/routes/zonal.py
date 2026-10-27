import logging

from fastapi import APIRouter
from nkz_platform_sdk import AuthContext
from pydantic import BaseModel, field_validator
from shapely.geometry import shape

from nkz_soil.api.dependencies import require_auth
from nkz_soil.api.limiter import limiter
from nkz_soil.api.routes.reading import _first_agri_soil, _prop_value
from nkz_soil.services.zonal import resolve_zone_soil_cached
from nkz_soil.storage.orion import OrionClient
from nkz_soil.util.nodata import sanitize_horizons

router = APIRouter()
logger = logging.getLogger(__name__)
_REQUIRE_AUTH = require_auth()

MAX_ZONES = 20


class ZoneIn(BaseModel):
    zoneId: str
    zoneVersion: str
    geometry: dict

    @field_validator("geometry")
    @classmethod
    def _polygonal(cls, g: dict) -> dict:
        if g.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError("geometry must be a Polygon or MultiPolygon")
        try:
            if shape(g).is_empty:
                raise ValueError("geometry is empty")
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ValueError(f"invalid geometry: {exc}") from exc
        return g


class ZonalRequest(BaseModel):
    parcel_id: str
    depth: str = "0-60"
    zones: list[ZoneIn]

    @field_validator("depth")
    @classmethod
    def _depth(cls, d: str) -> str:
        try:
            lo, hi = (int(x) for x in d.split("-"))
        except ValueError as exc:
            raise ValueError("depth must look like '0-60'") from exc
        if lo < 0 or hi <= lo:
            raise ValueError("depth must look like '0-60'")
        return d

    @field_validator("zones")
    @classmethod
    def _zones(cls, z: list[ZoneIn]) -> list[ZoneIn]:
        if not z:
            raise ValueError("at least one zone is required")
        if len(z) > MAX_ZONES:
            raise ValueError(f"at most {MAX_ZONES} zones per request")
        return z


@router.post("/zonal")
@limiter.exempt
async def zonal_soil(body: ZonalRequest, auth: AuthContext = _REQUIRE_AUTH):
    async with OrionClient(auth.tenant_id) as orion:
        entity = await _first_agri_soil(orion, body.parcel_id)
    location = _prop_value(entity, "location") or {}
    parcel_summary = {
        "horizons": sanitize_horizons(_prop_value(entity, "horizons", []) or []),
        "dataSource": _prop_value(entity, "dataSource", ""),
        "parcelGeometry": location if isinstance(location, dict) and location.get("coordinates") else None,
    }
    ctx: dict = {}  # per-request memo (parcel-level IDENA classes)
    zones = []
    for zone in body.zones:
        zones.append(
            await resolve_zone_soil_cached(
                auth.tenant_id, body.parcel_id, parcel_summary, zone.model_dump(), body.depth, ctx
            )
        )
    return {"parcel_id": body.parcel_id, "zones": zones}
