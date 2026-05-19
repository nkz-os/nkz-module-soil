import csv
import io
import math
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


LUCAS_CSV_URLS = [
    "https://esdac.jrc.ec.europa.eu/public_path/shared_folder/dataset/77/LUCAS_2022_TOPSOIL.csv",
    "https://esdac.jrc.ec.europa.eu/public_path/shared_folder/dataset/77/LUCAS2022_SOIL.csv",
]

SEARCH_RADIUS_KM = 50
MAX_POINTS = 5


class LucasProvider:
    name = "lucas"
    priority = 25
    geographic_scope = GeographicScope(
        bbox=(-10, 35, 35, 70),
        countries=[
            "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR",
            "GB", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL",
            "PL", "PT", "RO", "SE", "SI", "SK",
        ],
    )
    update_cadence = timedelta(days=365)
    attribution = "European Commission, Joint Research Centre (JRC), LUCAS Topsoil Survey"

    def __init__(self):
        self._cache: list[dict] | None = None
        self._cache_time: datetime | None = None
        self._load_failed = False

    def covers(self, geometry: dict) -> bool:
        return geometry_intersects_bbox(geometry, self.geographic_scope.bbox)

    async def fetch(
        self,
        geometry: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult:
        lon, lat = self._get_centroid(geometry)

        if self._cache is None and not self._load_failed:
            await self._load_csv_cache()

        if self._cache is None:
            return SoilDataResult(
                provider=self.name, horizons=[], uncertainty=0.10, geometry=geometry
            )

        nearby_points = self._find_nearby_points(lon, lat, SEARCH_RADIUS_KM)
        if not nearby_points:
            return SoilDataResult(
                provider=self.name, horizons=[], uncertainty=0.10, geometry=geometry
            )

        horizons = self._parse_lucas_points(nearby_points, properties, depths)

        return SoilDataResult(
            provider=self.name,
            horizons=horizons,
            uncertainty=0.10,
            geometry=geometry,
            attribution=self.attribution,
        )

    async def _load_csv_cache(self):
        for url in LUCAS_CSV_URLS:
            try:
                async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    text = resp.text
                    self._cache = self._parse_csv(text)
                    self._cache_time = datetime.now()
                    return
            except Exception:
                continue
        self._load_failed = True

    def _parse_csv(self, text: str) -> list[dict]:
        points = []
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            try:
                lat = float(row.get("POINT_LAT", row.get("lat", 0)))
                lon = float(row.get("POINT_LONG", row.get("lon", 0)))
                if lat == 0 and lon == 0:
                    continue
                points.append({
                    "point_id": row.get("POINT_ID"),
                    "lat": lat,
                    "lon": lon,
                    "sand": self._safe_float(row.get("Sand")),
                    "silt": self._safe_float(row.get("Silt")),
                    "clay": self._safe_float(row.get("Clay")),
                    "oc": self._safe_float(row.get("OC", row.get("organic_carbon"))),
                    "ph_cacl2": self._safe_float(row.get("pH_CaCl2")),
                    "ph_h2o": self._safe_float(row.get("pH_H2O")),
                    "bulk_density": self._safe_float(row.get("Bulk_density", row.get("bulk_density"))),
                    "cec": self._safe_float(row.get("CEC", row.get("cec"))),
                    "coarse": self._safe_float(row.get("Coarse", row.get("coarse_fragments"))),
                    "nitrogen": self._safe_float(row.get("N", row.get("nitrogen"))),
                    "phosphorus": self._safe_float(row.get("P", row.get("phosphorus"))),
                    "potassium": self._safe_float(row.get("K", row.get("potassium"))),
                })
            except (ValueError, TypeError, KeyError):
                continue
        return points

    def _find_nearby_points(self, lon: float, lat: float, radius_km: float) -> list[dict]:
        if not self._cache:
            return []
        nearby = []
        for point in self._cache:
            dist = self._haversine(lat, lon, point["lat"], point["lon"])
            if dist <= radius_km:
                nearby.append((dist, point))
        nearby.sort(key=lambda x: x[0])
        return [p for _, p in nearby[:MAX_POINTS]]

    def _parse_lucas_points(
        self, points: list[dict], properties: list[SoilProperty], depths: list[DepthInterval]
    ) -> list[Horizon]:
        if not points:
            return []

        avg: dict[str, float | None] = {
            "sand": None, "silt": None, "clay": None, "oc": None,
            "ph": None, "bulk_density": None, "cec": None, "coarse": None,
        }
        counts: dict[str, int] = {k: 0 for k in avg}

        for point in points:
            for key in ["sand", "silt", "clay", "oc", "bulk_density", "cec", "coarse"]:
                val = point.get(key)
                if val is not None:
                    avg[key] = (avg[key] or 0) + val
                    counts[key] += 1
            ph_val = point.get("ph_cacl2") or point.get("ph_h2o")
            if ph_val is not None:
                avg["ph"] = (avg["ph"] or 0) + ph_val
                counts["ph"] += 1

        for key in avg:
            if counts[key] > 0 and avg[key] is not None:
                avg[key] = avg[key] / counts[key]

        horizons = []
        for depth in depths:
            horizon_data: dict[str, Any] = {
                "depth_from": depth.depth_from,
                "depth_to": depth.depth_to,
            }
            if avg["sand"] is not None and SoilProperty.SAND in properties:
                horizon_data["sand"] = round(avg["sand"], 1)
            if avg["silt"] is not None and SoilProperty.SILT in properties:
                horizon_data["silt"] = round(avg["silt"], 1)
            if avg["clay"] is not None and SoilProperty.CLAY in properties:
                horizon_data["clay"] = round(avg["clay"], 1)
            if avg["oc"] is not None and SoilProperty.ORGANIC_CARBON in properties:
                horizon_data["organic_carbon"] = round(avg["oc"], 2)
            if avg["ph"] is not None and SoilProperty.PH in properties:
                horizon_data["ph"] = round(avg["ph"], 2)
            if avg["bulk_density"] is not None and SoilProperty.BULK_DENSITY in properties:
                horizon_data["bulk_density"] = round(avg["bulk_density"], 2)
            if avg["cec"] is not None and SoilProperty.CEC in properties:
                horizon_data["cec"] = round(avg["cec"], 2)
            if avg["coarse"] is not None and SoilProperty.COARSE_FRAGMENTS in properties:
                horizon_data["coarse_fragments"] = round(avg["coarse"], 1)
            horizons.append(Horizon(**horizon_data))

        return horizons

    def _safe_float(self, val: str | None) -> float | None:
        if val is None or val == "" or val == "NA":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def _haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

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
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                for url in LUCAS_CSV_URLS:
                    resp = await client.head(url)
                    if resp.status_code < 400:
                        return ProviderHealth(
                            name=self.name,
                            status="ok",
                            latency_ms=resp.elapsed.total_seconds() * 1000,
                            last_success=datetime.now(),
                            error_count=0,
                            cache_hit_rate=0.0,
                        )
                return ProviderHealth(
                    name=self.name,
                    status="degraded",
                    latency_ms=0,
                    last_success=None,
                    error_count=1,
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
