import asyncio
import logging
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

logger = logging.getLogger(__name__)

REST_BASE_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
WEBDAV_BASE_URL = "https://files.isric.org/soilgrids/latest/data/"

RATE_LIMIT_CALLS = 5
RATE_LIMIT_WINDOW_SEC = 60
MAX_RETRIES = 3

PROPERTY_TO_WEBDAV_NAME = {
    SoilProperty.SAND: "sand",
    SoilProperty.SILT: "silt",
    SoilProperty.CLAY: "clay",
    SoilProperty.ORGANIC_CARBON: "soc",
    SoilProperty.BULK_DENSITY: "bdod",
    SoilProperty.PH: "phh2o",
    SoilProperty.CEC: "cec",
    SoilProperty.COARSE_FRAGMENTS: "cfvo",
}

PROPERTY_TO_REST_NAME = {
    SoilProperty.SAND: "sand",
    SoilProperty.SILT: "silt",
    SoilProperty.CLAY: "clay",
    SoilProperty.ORGANIC_CARBON: "ocd",
    SoilProperty.BULK_DENSITY: "bdod",
    SoilProperty.PH: "phh2o",
    SoilProperty.CEC: "cec",
    SoilProperty.COARSE_FRAGMENTS: "cfvo",
}

UNIT_FACTORS = {
    "sand": 10.0,
    "silt": 10.0,
    "clay": 10.0,
    "soc": 10.0,
    "bdod": 1000.0,
    "phh2o": 10.0,
    "cec": 10.0,
    "cfvo": 10.0,
    "ocd": 10.0,
    "nitrogen": 10.0,
}

DEPTH_LEVELS = [0, 5, 15, 30, 60, 100, 200]


def _build_cog_url(property_name: str, depth_from: int, depth_to: int, statistic: str = "mean") -> str:
    return f"{WEBDAV_BASE_URL}{property_name}/{property_name}_{depth_from}-{depth_to}cm_{statistic}.vrt"


def _depth_to_soilgrids_range(depth_from: int, depth_to: int) -> tuple[int, int]:
    mapping = {
        (0, 5): (0, 5),
        (5, 15): (5, 15),
        (15, 30): (15, 30),
        (30, 60): (30, 60),
        (60, 100): (60, 100),
        (100, 200): (100, 200),
    }
    return mapping.get((depth_from, depth_to), (depth_from, depth_to))


class SoilGridsProvider:
    name = "soilgrids"
    priority = 10
    geographic_scope = GeographicScope(
        bbox=(-180, -90, 180, 90),
        countries=["*"],
    )
    update_cadence = timedelta(days=365)
    rate_limit_calls = RATE_LIMIT_CALLS
    rate_limit_window_sec = RATE_LIMIT_WINDOW_SEC
    attribution = "ISRIC World Soil Information, SoilGrids v2.0"
    use_webdav = True

    def __init__(self):
        self._call_times: list[float] = []

    def covers(self, geometry: dict) -> bool:
        return geometry_intersects_bbox(geometry, self.geographic_scope.bbox)

    async def fetch(
        self,
        geometry: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult:
        lon, lat = self._get_centroid(geometry)

        if self.use_webdav:
            return await self._fetch_webdav(lon, lat, geometry, properties, depths)
        return await self._fetch_rest(lon, lat, geometry, properties, depths)

    async def _fetch_webdav(
        self,
        lon: float,
        lat: float,
        geometry: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult:
        try:
            import rasterio
            from rasterio.windows import Window
        except ImportError:
            logger.warning("rasterio not available, falling back to REST API")
            return await self._fetch_rest(lon, lat, geometry, properties, depths)

        horizons = []
        for depth in depths:
            horizon_data: dict[str, Any] = {
                "depth_from": depth.depth_from,
                "depth_to": depth.depth_to,
            }

            for prop in properties:
                if prop not in PROPERTY_TO_WEBDAV_NAME:
                    continue
                webdav_name = PROPERTY_TO_WEBDAV_NAME[prop]
                sg_from, sg_to = _depth_to_soilgrids_range(depth.depth_from, depth.depth_to)
                cog_url = _build_cog_url(webdav_name, sg_from, sg_to, "mean")

                try:
                    value = await asyncio.to_thread(
                        self._read_cog_pixel, rasterio, cog_url, lon, lat
                    )
                    if value is not None and value != -9999:
                        factor = UNIT_FACTORS.get(webdav_name, 1.0)
                        horizon_data[self._map_layer_name(webdav_name)] = round(value / factor, 2)
                except Exception as e:
                    logger.warning("Failed to read COG %s: %s", cog_url, e)

            horizons.append(Horizon(**horizon_data))

        return SoilDataResult(
            provider=self.name,
            horizons=horizons,
            uncertainty=0.25,
            geometry=geometry,
            attribution=self.attribution,
        )

    def _read_cog_pixel(self, rasterio, cog_url: str, lon: float, lat: float) -> float | None:
        vsi_url = f"/vsicurl/{cog_url}"
        with rasterio.open(vsi_url) as src:
            row, col = src.index(lon, lat)
            window = Window(col, row, 1, 1)
            data = src.read(1, window=window)
            if data.size > 0:
                return float(data[0, 0])
        return None

    async def _fetch_rest(
        self,
        lon: float,
        lat: float,
        geometry: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult:
        await self._enforce_rate_limit()

        rest_properties = [p for p in properties if p in PROPERTY_TO_REST_NAME]
        if not rest_properties:
            return SoilDataResult(
                provider=self.name, horizons=[], uncertainty=0.25, geometry=geometry
            )

        payload = {
            "lon": lon,
            "lat": lat,
            "property": [PROPERTY_TO_REST_NAME[p] for p in rest_properties],
            "depth": [f"{d.depth_from}-{d.depth_to}cm" for d in depths],
        }

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(REST_BASE_URL, params=payload)
                    if resp.status_code == 429:
                        wait_time = RATE_LIMIT_WINDOW_SEC * (attempt + 1)
                        await asyncio.sleep(wait_time)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    self._record_call()
                    return self._parse_response(data, rest_properties, depths, geometry)
            except httpx.HTTPStatusError:
                if attempt == MAX_RETRIES - 1:
                    return SoilDataResult(
                        provider=self.name, horizons=[], uncertainty=0.25, geometry=geometry
                    )
                await asyncio.sleep(RATE_LIMIT_WINDOW_SEC * (attempt + 1))

        return SoilDataResult(
            provider=self.name, horizons=[], uncertainty=0.25, geometry=geometry
        )

    async def _enforce_rate_limit(self):
        now = asyncio.get_event_loop().time()
        self._call_times = [
            t for t in self._call_times if now - t < RATE_LIMIT_WINDOW_SEC
        ]
        if len(self._call_times) >= RATE_LIMIT_CALLS:
            wait_time = RATE_LIMIT_WINDOW_SEC - (now - self._call_times[0])
            if wait_time > 0:
                await asyncio.sleep(wait_time)

    def _record_call(self):
        now = asyncio.get_event_loop().time()
        self._call_times.append(now)

    def _parse_response(
        self,
        data: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
        geometry: dict,
    ) -> SoilDataResult:
        layers = data.get("properties", {}).get("layers", [])
        horizons = []

        for depth in depths:
            horizon_data: dict[str, Any] = {
                "depth_from": depth.depth_from,
                "depth_to": depth.depth_to,
            }
            for layer in layers:
                name = layer.get("name", "")
                for d in layer.get("depths", []):
                    if (
                        d.get("range", {}).get("top_depth") == depth.depth_from
                        and d.get("range", {}).get("bottom_depth") == depth.depth_to
                    ):
                        value = d.get("values", {}).get("mean", 0)
                        unit_factor = layer.get("unit_measure", {}).get("d_factor", 1)
                        mapped_name = self._map_layer_name(name)
                        horizon_data[mapped_name] = round(value * unit_factor, 2)
            horizons.append(Horizon(**horizon_data))

        return SoilDataResult(
            provider=self.name,
            horizons=horizons,
            uncertainty=0.25,
            geometry=geometry,
            attribution=self.attribution,
        )

    def _map_layer_name(self, name: str) -> str:
        mapping = {
            "sand": "sand",
            "silt": "silt",
            "clay": "clay",
            "ocd": "organic_carbon",
            "bdod": "bulk_density",
            "phh2o": "ph",
            "cec": "cec",
            "cfvo": "coarse_fragments",
            "soc": "organic_carbon",
            "nitrogen": "nitrogen",
        }
        return mapping.get(name, name)

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
                resp = await client.get(WEBDAV_BASE_URL)
                return ProviderHealth(
                    name=self.name,
                    status="ok" if resp.status_code < 400 else "degraded",
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
