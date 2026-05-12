from datetime import timedelta, datetime
import httpx
from nkz_soil.models.domain import SoilProperty, DepthInterval, SoilDataResult, ProviderHealth, GeographicScope, Horizon


class EuSoilHydroGridsProvider:
    name = "eu_soil_hydro"
    priority = 20
    geographic_scope = GeographicScope(bbox=(-10, 35, 35, 70), countries=["AT","BE","BG","CY","CZ","DE","DK","EE","ES","FI","FR","GB","GR","HR","HU","IE","IT","LT","LU","LV","MT","NL","PL","PT","RO","SE","SI","SK"])
    update_cadence = timedelta(days=365)
    BASE_URL = "https://esdac.jrc.ec.europa.eu"

    def covers(self, geometry: dict) -> bool:
        return True

    async def fetch(self, geometry: dict, properties: list[SoilProperty], depths: list[DepthInterval]) -> SoilDataResult:
        return SoilDataResult(provider=self.name, horizons=[], uncertainty=0.20, geometry=geometry)

    async def health(self) -> ProviderHealth:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(self.BASE_URL)
                return ProviderHealth(name=self.name, status="ok", latency_ms=resp.elapsed.total_seconds() * 1000,
                                      last_success=datetime.now(), error_count=0, cache_hit_rate=0.0)
        except Exception:
            return ProviderHealth(name=self.name, status="down", latency_ms=0,
                                  last_success=None, error_count=1, cache_hit_rate=0.0)
