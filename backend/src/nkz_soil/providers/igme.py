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


BASE_URL = "https://mapas.igme.es/gis/services/Cartografia_Geologica/IGME_MAGNA_50/MapServer/WMSServer"

LITHOLOGY_LAYERS = ["0"]

LITHOLOGY_TO_HYDROLOGIC_GROUP = {
    "grava": "A",
    "gravas": "A",
    "arena": "A",
    "arenas": "A",
    "arenisca": "A",
    "caliza": "B",
    "calizas": "B",
    "marga": "C",
    "margas": "C",
    "arcilla": "D",
    "arcillas": "D",
    "limo": "C",
    "limos": "C",
    "yeso": "C",
    "yesos": "C",
    "granito": "B",
    "gneis": "B",
    "pizarra": "C",
    "cuarcita": "B",
    "esquisto": "C",
    "diorita": "B",
    "basalto": "B",
    "andesita": "B",
    "riolita": "B",
    "toba": "A",
    "ceniza": "A",
    "coluvion": "B",
    "coluviones": "B",
    "aluvion": "A",
    "aluviones": "A",
    "turba": "D",
    "marga yesifera": "C",
    "margas yesiferas": "C",
    "conglomerado": "A",
    "conglomerados": "A",
    "cauce actual": "A",
}


class IgmeProvider:
    name = "igme"
    priority = 30
    geographic_scope = GeographicScope(bbox=(-10, 35, 5, 44), countries=["ES"])
    update_cadence = timedelta(days=365)

    def covers(self, geometry: dict) -> bool:
        return geometry_intersects_bbox(geometry, self.geographic_scope.bbox)

    async def fetch(
        self,
        geometry: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult:
        lon, lat = self._get_centroid(geometry)
        bbox = f"{lon-0.01},{lat-0.01},{lon+0.01},{lat+0.01}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            params: dict[str, str | int] = {
                "service": "WMS",
                "version": "1.1.1",
                "request": "GetFeatureInfo",
                "layers": ",".join(LITHOLOGY_LAYERS),
                "query_layers": ",".join(LITHOLOGY_LAYERS),
                "info_format": "text/html",
                "width": 256,
                "height": 256,
                "srs": "EPSG:4326",
                "bbox": bbox,
                "x": 128,
                "y": 128,
            }
            resp = await client.get(BASE_URL, params=params)
            if resp.status_code != 200:
                return SoilDataResult(
                    provider=self.name, horizons=[], uncertainty=0.20, geometry=geometry
                )
            text = resp.text

        horizons = self._parse_html_response(text, properties, depths)

        return SoilDataResult(
            provider=self.name,
            horizons=horizons,
            uncertainty=0.20,
            geometry=geometry,
        )

    def _parse_html_response(
        self, text: str, properties: list[SoilProperty], depths: list[DepthInterval]
    ) -> list[Horizon]:
        horizons: list[Horizon] = []
        lithology = self._extract_lithology_from_html(text)
        hydro_group = self._classify_hydrologic_group(lithology)

        for depth in depths:
            horizon_data: dict[str, Any] = {
                "depth_from": depth.depth_from,
                "depth_to": depth.depth_to,
            }
            if hydro_group and SoilProperty.HYDROLOGIC_GROUP in properties:
                horizon_data["hydrologic_group"] = hydro_group
            horizons.append(Horizon(**horizon_data))

        return horizons

    def _extract_lithology_from_html(self, text: str) -> str:
        import re
        match = re.search(r'descripción litológica[^<]*</th>[^<]*<td[^>]*>([^<]+)', text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        for pattern in [r'descripción[^<]*[:\s]*([^<\n]+)', r'lito[^<]*[:\s]*([^<\n]+)']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _classify_hydrologic_group(self, lithology: str) -> str | None:
        if not lithology:
            return None
        lithology_lower = lithology.lower()
        for key, group in LITHOLOGY_TO_HYDROLOGIC_GROUP.items():
            if key in lithology_lower:
                return group
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
                    f"{BASE_URL}?service=WMS&request=GetCapabilities&version=1.1.1"
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
