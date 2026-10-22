import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from shapely.geometry import Point, shape

from nkz_soil.models.domain import (
    DepthInterval,
    GeographicScope,
    Horizon,
    ProviderHealth,
    SoilDataResult,
    SoilProperty,
)
from nkz_soil.providers.base import geometry_intersects_bbox

logger = logging.getLogger(__name__)

WFS_URL = "https://idena.navarra.es/ogc/wfs"

SOIL_LAYERS = [
    "IDENA:EDAFOL_Pol_Suelos25m",
    "IDENA:EDAFOL_Pol_REDRurbasa",
]

# Half-side (degrees) of the bbox used to fetch recintos around the parcel
# point; the recinto that actually contains the point is picked client-side.
_SEARCH_HALF_DEG = 0.002

# Surface horizon only. IDENA's CLASIF_HS1 is the "clase textural del horizonte
# superficial" (series sheets: Ap, ~0-33 cm); CLASIF_SC1 is the family class of
# the control section and is too broad to turn into fractions.
_SURFACE_MAX_DEPTH_CM = 30

# USDA texture class (IDENA Spanish label) -> representative (sand, silt, clay) %
# inside that class of the USDA texture triangle, so the class re-derives
# unchanged. Class-level approximation, not a measurement.
TEXTURE_CLASS_FRACTIONS: dict[str, tuple[float, float, float]] = {
    "Arenosa": (92.0, 5.0, 3.0),
    "Arenosa franca": (82.0, 12.0, 6.0),
    "Franco arenosa": (65.0, 25.0, 10.0),
    "Franca": (40.0, 40.0, 20.0),
    "Franco limosa": (20.0, 65.0, 15.0),
    "Limosa": (7.0, 88.0, 5.0),
    "Franco arcillo arenosa": (60.0, 13.0, 27.0),
    "Franco arcillosa": (32.0, 34.0, 34.0),
    "Franco arcillo limosa": (10.0, 56.0, 34.0),
    "Arcillo arenosa": (52.0, 6.0, 42.0),
    "Arcillo limosa": (7.0, 46.0, 47.0),
    "Arcillosa": (20.0, 20.0, 60.0),
}


class IdenaProvider:
    name = "idena"
    priority = 40
    geographic_scope = GeographicScope(bbox=(-2.5, 41.5, -0.5, 43.5), countries=["ES"])
    update_cadence = timedelta(days=90)
    attribution = "Servicio proporcionado por el Gobierno de Navarra (CC BY 4.0 ES)"

    def covers(self, geometry: dict) -> bool:
        return geometry_intersects_bbox(geometry, self.geographic_scope.bbox)

    async def fetch(
        self,
        geometry: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult:
        lon, lat = self._representative_point(geometry)
        features = await self._get_features(lon, lat)
        horizons = self._surface_horizons(
            self._containing_feature(features, lon, lat), properties, depths
        )
        return SoilDataResult(
            provider=self.name,
            horizons=horizons,
            uncertainty=0.15,
            geometry=geometry,
            attribution=self.attribution,
        )

    async def _get_features(self, lon: float, lat: float) -> list[dict]:
        """Recintos around (lon, lat); IDENA returns lon/lat order in EPSG:4326."""
        d = _SEARCH_HALF_DEG
        params: dict[str, str | int] = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typename": ",".join(SOIL_LAYERS),
            "count": 50,
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
            "bbox": f"{lon - d},{lat - d},{lon + d},{lat + d},EPSG:4326",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(WFS_URL, params=params)
        if resp.status_code != 200:
            logger.warning("IDENA WFS returned %s for (%s, %s)", resp.status_code, lon, lat)
            return []
        return resp.json().get("features", [])

    @staticmethod
    def _containing_feature(features: list[dict], lon: float, lat: float) -> dict | None:
        point = Point(lon, lat)
        for feature in features:
            geom = feature.get("geometry")
            if geom and shape(geom).covers(point):
                return feature
        return None

    def _surface_horizons(
        self, feature: dict | None, properties: list[SoilProperty], depths: list[DepthInterval]
    ) -> list[Horizon]:
        if feature is None:
            return []
        label = (feature.get("properties", {}).get("CLASIF_HS1") or "").split(",")[0].strip()
        fractions = TEXTURE_CLASS_FRACTIONS.get(label)
        if fractions is None:
            return []
        sand, silt, clay = fractions

        horizons: list[Horizon] = []
        for depth in depths:
            if depth.depth_to > _SURFACE_MAX_DEPTH_CM:
                continue
            horizon_data: dict[str, Any] = {
                "depth_from": depth.depth_from,
                "depth_to": depth.depth_to,
            }
            if SoilProperty.SAND in properties:
                horizon_data["sand"] = sand
            if SoilProperty.SILT in properties:
                horizon_data["silt"] = silt
            if SoilProperty.CLAY in properties:
                horizon_data["clay"] = clay
            horizons.append(Horizon(**horizon_data))
        return horizons

    @staticmethod
    def _representative_point(geometry: dict) -> tuple[float, float]:
        """A point guaranteed inside the parcel (Polygon or MultiPolygon)."""
        point = shape(geometry).representative_point()
        return point.x, point.y

    async def health(self) -> ProviderHealth:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{WFS_URL}?service=WFS&request=GetCapabilities&version=2.0.0"
                )
                return ProviderHealth(
                    name=self.name,
                    status="ok",
                    latency_ms=resp.elapsed.total_seconds() * 1000,
                    last_success=datetime.now(tz=UTC),
                    error_count=0,
                    cache_hit_rate=0.0,
                )
        except Exception:  # noqa: BLE001 — health check must never fail; provider errors become status=down
            return ProviderHealth(
                name=self.name,
                status="down",
                latency_ms=0,
                last_success=None,
                error_count=1,
                cache_hit_rate=0.0,
            )
