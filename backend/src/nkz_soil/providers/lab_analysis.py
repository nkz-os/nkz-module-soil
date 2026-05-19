from datetime import timedelta, datetime

from nkz_soil.models.domain import (
    SoilProperty,
    DepthInterval,
    SoilDataResult,
    ProviderHealth,
    GeographicScope,
    Horizon,
)
from nkz_soil.providers.base import geometry_intersects_bbox
from nkz_soil.storage.orion import OrionClient


class LabAnalysisProvider:
    name = "lab_analysis"
    priority = 100
    geographic_scope = GeographicScope(bbox=(-180, -90, 180, 90), countries=["*"])
    update_cadence = timedelta(days=1)

    def covers(self, geometry: dict) -> bool:
        return geometry_intersects_bbox(geometry, self.geographic_scope.bbox)

    async def fetch(
        self,
        geometry: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult:
        async with OrionClient() as orion:
            points = await orion.query_entities(
                type="SoilSamplingPoint",
                geometry=geometry,
            )

        if not points:
            return SoilDataResult(
                provider=self.name, horizons=[], uncertainty=0.02, geometry=geometry
            )

        all_horizons = []
        for point in points:
            raw_horizons = point.get("horizons", {}).get("value", [])
            for h in raw_horizons:
                h_obj = Horizon(
                    depth_from=h.get("depthFrom", 0),
                    depth_to=h.get("depthTo", 100),
                    sand=h.get("sand"),
                    silt=h.get("silt"),
                    clay=h.get("clay"),
                    organic_carbon=h.get("organicCarbon"),
                    bulk_density=h.get("bulkDensity"),
                    ph=h.get("ph"),
                    cec=h.get("cec"),
                    coarse_fragments=h.get("coarseFragments"),
                    penetration_resistance=h.get("penetrationResistance"),
                )
                all_horizons.append(h_obj)

        return SoilDataResult(
            provider=self.name,
            horizons=all_horizons,
            uncertainty=0.02,
            geometry=geometry,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            name=self.name,
            status="ok",
            latency_ms=0,
            last_success=datetime.now(),
            error_count=0,
            cache_hit_rate=0.0,
        )
