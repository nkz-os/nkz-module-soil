from datetime import timedelta, datetime

import httpx

from nkz_soil.models.domain import (
    SoilProperty,
    DepthInterval,
    SoilDataResult,
    ProviderHealth,
    GeographicScope,
)
from nkz_soil.providers.base import geometry_intersects_bbox


LICENSE_WARNING = (
    "EU-SoilHydroGrids is licensed 'Free for non-commercial use' only. "
    "Commercial/SaaS use requires separate licensing. "
    "Consider deriving hydraulic parameters from SoilGrids + pedotransfer instead."
)

DEPTH_LEVELS_CM = [0, 5, 15, 30, 60, 100, 200]

JRC_CATALOGUE_URL = "https://data.jrc.ec.europa.eu/dataset/jrc-esdac-108"


class EuSoilHydroGridsProvider:
    name = "eu_soil_hydro"
    priority = 20
    geographic_scope = GeographicScope(
        bbox=(-10, 35, 35, 70),
        countries=[
            "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR",
            "GB", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL",
            "PL", "PT", "RO", "SE", "SI", "SK",
        ],
    )
    update_cadence = timedelta(days=365)
    license_restricted = True
    license_warning = LICENSE_WARNING
    requires_registration = True

    def covers(self, geometry: dict) -> bool:
        return geometry_intersects_bbox(geometry, self.geographic_scope.bbox)

    async def fetch(
        self,
        geometry: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult:
        return SoilDataResult(
            provider=self.name,
            horizons=[],
            uncertainty=0.20,
            geometry=geometry,
            attribution="JRC ESDAC EU-SoilHydroGrids v1.0 (non-commercial use only)",
        )

    async def health(self) -> ProviderHealth:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.head(JRC_CATALOGUE_URL)
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
