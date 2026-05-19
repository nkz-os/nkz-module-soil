from datetime import timedelta, datetime
from typing import Any

import httpx

from nkz_soil.models.domain import (
    SoilProperty,
    DepthInterval,
    SoilDataResult,
    ProviderHealth,
    GeographicScope,
    Horizon,
)
from nkz_soil.providers.base import geometry_intersects_bbox


BASE_URL = "https://map.bgs.ac.uk/arcgis/services/UKSO/UKSO_BGS/MapServer/WMSServer"

SOIL_LAYERS = [
    "Soil.depth.from.boreholes",
    "Parent.Material.Soil.texture.1km",
    "Parent.Material.Soil.texture.simple.1km",
    "Parent.Material.Grain.size",
]

TEXTURE_CLASS_TO_PROPERTIES = {
    "sand": {"sand": 90.0, "silt": 5.0, "clay": 5.0},
    "loamy sand": {"sand": 80.0, "silt": 10.0, "clay": 10.0},
    "sandy loam": {"sand": 60.0, "silt": 25.0, "clay": 15.0},
    "loam": {"sand": 45.0, "silt": 35.0, "clay": 20.0},
    "silt loam": {"sand": 20.0, "silt": 60.0, "clay": 20.0},
    "silt": {"sand": 10.0, "silt": 80.0, "clay": 10.0},
    "clay loam": {"sand": 30.0, "silt": 30.0, "clay": 40.0},
    "silty clay loam": {"sand": 10.0, "silt": 55.0, "clay": 35.0},
    "sandy clay": {"sand": 45.0, "silt": 10.0, "clay": 45.0},
    "silty clay": {"sand": 5.0, "silt": 45.0, "clay": 50.0},
    "clay": {"sand": 10.0, "silt": 15.0, "clay": 75.0},
    "peat": {"organic_carbon": 40.0},
    "made ground": {"organic_carbon": 5.0},
    "topsoil": {"organic_carbon": 3.5},
    "subsoil": {"organic_carbon": 1.5},
}


class BgsProvider:
    name = "bgs"
    priority = 30
    geographic_scope = GeographicScope(bbox=(-8, 49, 2, 61), countries=["GB"])
    update_cadence = timedelta(days=365)
    attribution = "UKRI / British Geological Survey and Cranfield University LandIS Portal"

    def covers(self, geometry: dict) -> bool:
        return geometry_intersects_bbox(geometry, self.geographic_scope.bbox)

    async def fetch(
        self,
        geometry: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult:
        lon, lat = self._get_centroid(geometry)
        bbox = f"{lat-0.01},{lon-0.01},{lat+0.01},{lon+0.01}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            params: dict[str, str | int] = {
                "service": "WMS",
                "version": "1.3.0",
                "request": "GetFeatureInfo",
                "layers": ",".join(SOIL_LAYERS),
                "query_layers": ",".join(SOIL_LAYERS),
                "info_format": "application/geo+json",
                "width": 256,
                "height": 256,
                "srs": "EPSG:4326",
                "bbox": bbox,
                "i": 128,
                "j": 128,
            }
            resp = await client.get(BASE_URL, params=params)
            if resp.status_code != 200:
                return SoilDataResult(
                    provider=self.name, horizons=[], uncertainty=0.20, geometry=geometry
                )
            data = resp.json()

        horizons = self._parse_geojson_features(data, properties, depths)

        return SoilDataResult(
            provider=self.name,
            horizons=horizons,
            uncertainty=0.20,
            geometry=geometry,
            attribution=self.attribution,
        )

    def _parse_geojson_features(
        self, data: dict, properties: list[SoilProperty], depths: list[DepthInterval]
    ) -> list[Horizon]:
        horizons: list[Horizon] = []
        features = data.get("features", [])
        if not features:
            return horizons

        props = features[0].get("properties", {})
        texture = self._extract_texture(props)
        prop_values = TEXTURE_CLASS_TO_PROPERTIES.get(texture.lower() if texture else "", {})

        for depth in depths:
            horizon_data: dict[str, Any] = {
                "depth_from": depth.depth_from,
                "depth_to": depth.depth_to,
            }
            for key, value in prop_values.items():
                soil_prop = self._key_to_soil_property(key)
                if soil_prop and soil_prop in properties:
                    horizon_data[key] = value
            horizons.append(Horizon(**horizon_data))

        return horizons

    def _extract_texture(self, props: dict) -> str:
        for key in ["texture", "soil_texture", "Value", "VALUE", "INTERPRETA"]:
            for k, v in props.items():
                if k.lower() == key.lower() and v is not None:
                    return str(v)
        return ""

    def _key_to_soil_property(self, key: str) -> SoilProperty | None:
        mapping = {
            "sand": SoilProperty.SAND,
            "silt": SoilProperty.SILT,
            "clay": SoilProperty.CLAY,
            "organic_carbon": SoilProperty.ORGANIC_CARBON,
        }
        return mapping.get(key)

    def _get_centroid(self, geometry: dict) -> tuple[float, float]:
        if geometry.get("type") == "Point":
            coords = geometry.get("coordinates", [0, 0])
            return coords[0], coords[1]
        if geometry.get("type") == "Polygon":
            coords = geometry.get("coordinates", [[[]]])[0]
            lon = sum(c[0] for c in coords) / len(coords)
            lat = sum(c[1] for c in coords) / len(coords)
            return lon, lat
        return 0.0, 0.0

    async def health(self) -> ProviderHealth:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{BASE_URL}?service=WMS&request=GetCapabilities&version=1.3.0"
                )
                return ProviderHealth(
                    name=self.name,
                    status="ok",
                    latency_ms=resp.elapsed.total_seconds() * 1000,
                    last_success=datetime.now(),
                    error_count=0,
                    cache_hit_rate=0.0,
                )
        except Exception:
            return ProviderHealth(
                name=self.name,
                status="down",
                latency_ms=0,
                last_success=None,
                error_count=1,
                cache_hit_rate=0.0,
            )
