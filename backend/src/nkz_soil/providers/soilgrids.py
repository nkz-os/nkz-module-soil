from datetime import timedelta, datetime
import httpx
from nkz_soil.models.domain import (
    SoilProperty,
    DepthInterval,
    SoilDataResult,
    ProviderHealth,
    GeographicScope,
    Horizon,
)


class SoilGridsProvider:
    name = "soilgrids"
    priority = 10
    geographic_scope = GeographicScope(
        bbox=(-180, -90, 180, 90),
        countries=["*"],
    )
    update_cadence = timedelta(days=365)

    BASE_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

    def covers(self, geometry: dict) -> bool:
        return True

    async def fetch(
        self,
        geometry: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult:
        property_map = {
            SoilProperty.SAND: "sand",
            SoilProperty.SILT: "silt",
            SoilProperty.CLAY: "clay",
            SoilProperty.ORGANIC_CARBON: "ocd",
            SoilProperty.BULK_DENSITY: "bdod",
            SoilProperty.PH: "phh2o",
            SoilProperty.CEC: "cec",
            SoilProperty.COARSE_FRAGMENTS: "cfvo",
        }

        payload = {
            "query": geometry,
            "properties": [property_map[p] for p in properties if p in property_map],
            "depths": [f"{d.depth_from}-{d.depth_to}cm" for d in depths],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.BASE_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        return self._parse_response(data, properties, depths)

    def _parse_response(
        self,
        data: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult:
        layers = data["properties"]["layers"]
        horizons = []

        for depth in depths:
            horizon_data = {"depth_from": depth.depth_from, "depth_to": depth.depth_to}
            for layer in layers:
                name = layer["name"]
                for d in layer["depths"]:
                    if (
                        d["range"]["top_depth"] == depth.depth_from
                        and d["range"]["bottom_depth"] == depth.depth_to
                    ):
                        value = d["values"]["mean"] * layer["unit_measure"]["d_factor"]
                        horizon_data[self._map_layer_name(name)] = round(value, 2)
            horizons.append(Horizon(**horizon_data))

        return SoilDataResult(
            provider=self.name,
            horizons=horizons,
            uncertainty=0.25,
            geometry=data.get("geometry", {}),
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
        }
        return mapping.get(name, name)

    async def health(self) -> ProviderHealth:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(self.BASE_URL)
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
