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


WFS_URL = "https://idena.navarra.es/ogc/wfs"

SOIL_LAYERS = [
    "IDENA:EDAFOL_Pol_Suelos25m",
    "IDENA:EDAFOL_Pol_REDRurbasa",
    "IDENA:OCUPAC_Pol_REDRapti",
]

TEXTURE_CLASS_TO_SAND = {
    "arenoso": 85.0,
    "arena": 90.0,
    "franco-arenoso": 70.0,
    "franco": 40.0,
    "franco-arcilloso": 25.0,
    "arcilloso": 15.0,
    "arcilla": 10.0,
    "limo": 20.0,
    "franco-limoso": 30.0,
    "arcillo-limoso": 15.0,
}

TEXTURE_CLASS_TO_SILT = {
    "arenoso": 5.0,
    "arena": 5.0,
    "franco-arenoso": 15.0,
    "franco": 40.0,
    "franco-arcilloso": 20.0,
    "arcilloso": 15.0,
    "arcilla": 10.0,
    "limo": 70.0,
    "franco-limoso": 55.0,
    "arcillo-limoso": 60.0,
}

TEXTURE_CLASS_TO_CLAY = {
    "arenoso": 10.0,
    "arena": 5.0,
    "franco-arenoso": 15.0,
    "franco": 20.0,
    "franco-arcilloso": 55.0,
    "arcilloso": 70.0,
    "arcilla": 80.0,
    "limo": 10.0,
    "franco-limoso": 15.0,
    "arcillo-limoso": 25.0,
}

SOIL_TAXON_TO_PH = {
    "cambisol": 6.5,
    "luvisol": 6.0,
    "regosol": 7.0,
    "leptosol": 7.5,
    "fluvisol": 7.2,
    "calcisol": 8.0,
    "gleysol": 5.5,
    "stagnosol": 5.0,
    "podzol": 4.5,
}

SOIL_TAXON_TO_OC = {
    "cambisol": 2.5,
    "luvisol": 2.0,
    "regosol": 1.5,
    "leptosol": 3.0,
    "fluvisol": 2.8,
    "calcisol": 1.0,
    "gleysol": 4.0,
    "stagnosol": 5.0,
    "podzol": 6.0,
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
        lon, lat = self._get_centroid(geometry)

        async with httpx.AsyncClient(timeout=30.0) as client:
            params: dict[str, str | int] = {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typename": ",".join(SOIL_LAYERS),
                "count": 1,
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "bbox": f"{lon-0.01},{lat-0.01},{lon+0.01},{lat+0.01},EPSG:4326",
            }
            resp = await client.get(WFS_URL, params=params)
            if resp.status_code != 200:
                return SoilDataResult(
                    provider=self.name, horizons=[], uncertainty=0.15, geometry=geometry
                )
            data = resp.json()

        horizons = self._parse_wfs_features(data, properties, depths)

        return SoilDataResult(
            provider=self.name,
            horizons=horizons,
            uncertainty=0.15,
            geometry=geometry,
            attribution=self.attribution,
        )

    def _parse_wfs_features(
        self, data: dict, properties: list[SoilProperty], depths: list[DepthInterval]
    ) -> list[Horizon]:
        horizons: list[Horizon] = []
        features = data.get("features", [])
        if not features:
            return horizons

        props = features[0].get("properties", {})

        serie = self._extract_field(props, ["SERIE1", "SERIE2", "SERIE3"])
        geomorf = self._extract_field(props, ["GEOMORF1", "GEOMORF2", "GEOMORF3"])
        soil_taxon = self._extract_field(props, ["SOILTAXON1", "SOILTAXON2", "SOILTAXON3"])
        clasif_sc = self._extract_field(props, ["CLASIF_SC1", "CLASIF_SC2", "CLASIF_SC3"])

        texture_class = self._infer_texture_from_geomorf(geomorf)
        sand_val = TEXTURE_CLASS_TO_SAND.get(texture_class.lower() if texture_class else "")
        silt_val = TEXTURE_CLASS_TO_SILT.get(texture_class.lower() if texture_class else "")
        clay_val = TEXTURE_CLASS_TO_CLAY.get(texture_class.lower() if texture_class else "")
        ph_val = SOIL_TAXON_TO_PH.get(soil_taxon.lower() if soil_taxon else "")
        oc_val = SOIL_TAXON_TO_OC.get(soil_taxon.lower() if soil_taxon else "")

        for depth in depths:
            horizon_data: dict[str, Any] = {
                "depth_from": depth.depth_from,
                "depth_to": depth.depth_to,
            }
            if sand_val is not None and SoilProperty.SAND in properties:
                horizon_data["sand"] = sand_val
            if silt_val is not None and SoilProperty.SILT in properties:
                horizon_data["silt"] = silt_val
            if clay_val is not None and SoilProperty.CLAY in properties:
                horizon_data["clay"] = clay_val
            if ph_val is not None and SoilProperty.PH in properties:
                horizon_data["ph"] = ph_val
            if oc_val is not None and SoilProperty.ORGANIC_CARBON in properties:
                horizon_data["organic_carbon"] = oc_val
            horizons.append(Horizon(**horizon_data))

        return horizons

    def _infer_texture_from_geomorf(self, geomorf: str | None) -> str | None:
        if not geomorf:
            return None
        geomorf_lower = geomorf.lower()
        if "arena" in geomorf_lower or "sand" in geomorf_lower:
            return "arena"
        if "arcilla" in geomorf_lower or "clay" in geomorf_lower:
            return "arcilla"
        if "limo" in geomorf_lower or "silt" in geomorf_lower:
            return "limo"
        if "franco" in geomorf_lower or "loam" in geomorf_lower:
            return "franco"
        return None

    def _extract_field(self, props: dict, candidates: list[str]) -> str | None:
        for key in candidates:
            val = props.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        return None

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
                    f"{WFS_URL}?service=WFS&request=GetCapabilities&version=2.0.0"
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
