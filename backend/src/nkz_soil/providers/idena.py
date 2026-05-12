from datetime import timedelta, datetime
import httpx
from nkz_soil.models.domain import SoilProperty, DepthInterval, SoilDataResult, ProviderHealth, GeographicScope, Horizon


class IdenaProvider:
    name = "idena"
    priority = 40
    geographic_scope = GeographicScope(bbox=(-2.5, 41.5, -0.5, 43.5), countries=["ES"])
    update_cadence = timedelta(days=90)
    BASE_URL = "https://idena.navarra.es/ogc/wms"

    def covers(self, geometry: dict) -> bool:
        return True

    async def fetch(self, geometry: dict, properties: list[SoilProperty], depths: list[DepthInterval]) -> SoilDataResult:
        # WMS GetFeatureInfo — stub that returns empty for now (Phase 2 WMS integration)
        return SoilDataResult(provider=self.name, horizons=[], uncertainty=0.15, geometry=geometry)

    async def health(self) -> ProviderHealth:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.BASE_URL}?service=WMS&request=GetCapabilities")
                return ProviderHealth(name=self.name, status="ok", latency_ms=resp.elapsed.total_seconds() * 1000,
                                      last_success=datetime.now(), error_count=0, cache_hit_rate=0.0)
        except Exception:
            return ProviderHealth(name=self.name, status="down", latency_ms=0,
                                  last_success=None, error_count=1, cache_hit_rate=0.0)
