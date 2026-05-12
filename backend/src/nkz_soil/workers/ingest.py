from nkz_soil.providers.base import ProviderRegistry, CircuitBreaker
from nkz_soil.models.domain import SoilProperty, DepthInterval, Horizon
from nkz_soil.storage.orion import OrionClient
import uuid


STANDARD_DEPTHS = [
    DepthInterval(0, 5), DepthInterval(5, 15), DepthInterval(15, 30),
    DepthInterval(30, 60), DepthInterval(60, 100),
]

STANDARD_PROPERTIES = [
    SoilProperty.SAND, SoilProperty.SILT, SoilProperty.CLAY,
    SoilProperty.ORGANIC_CARBON, SoilProperty.BULK_DENSITY, SoilProperty.PH,
    SoilProperty.CEC, SoilProperty.COARSE_FRAGMENTS,
]

ALL_PROPERTIES = STANDARD_PROPERTIES + [
    SoilProperty.KSAT_SATURATED, SoilProperty.AVAILABLE_WATER_CAPACITY,
    SoilProperty.HYDROLOGIC_GROUP, SoilProperty.PENETRATION_RESISTANCE,
]

PROVIDER_PRIORITIES = {
    "lab_analysis": 100, "iot_sensor": 90, "idena": 40, "igme": 30,
    "bgs": 30, "lucas": 25, "eu_soil_hydro": 20, "soilgrids": 10,
}


async def startup(ctx):
    ctx["registry"] = ProviderRegistry()
    ctx["circuit_breaker"] = CircuitBreaker()


async def ingest_parcel(ctx, parcel_id: str, tenant_id: str, geometry: dict, parcel_version_id: str):
    registry = ctx["registry"]
    circuit_breaker = ctx["circuit_breaker"]

    all_results = []
    for provider in registry.get_all():
        if circuit_breaker.is_open(provider.name):
            continue
        if not provider.covers(geometry):
            continue
        try:
            result = await provider.fetch(geometry, ALL_PROPERTIES, STANDARD_DEPTHS)
            all_results.append(result)
            circuit_breaker.record_success(provider.name)
        except Exception:
            circuit_breaker.record_failure(provider.name)
            continue

    merged_horizons = _cascade_merge(all_results, STANDARD_DEPTHS)
    uncertainty = _aggregate_uncertainty(all_results)

    async with OrionClient(tenant_id) as orion:
        agri_soil = {
            "id": f"urn:ngsi-ld:AgriSoil:{uuid.uuid4()}",
            "type": "AgriSoil",
            "@context": ["https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"],
            "location": {"type": "GeoProperty", "value": geometry},
            "refAgriParcel": {"type": "Relationship", "object": f"urn:ngsi-ld:AgriParcel:{parcel_id}"},
            "parcelVersionId": {"type": "Property", "value": parcel_version_id},
            "horizons": {"type": "Property", "value": [_horizon_to_dict(h) for h in merged_horizons]},
            "dataSource": {"type": "Property", "value": _primary_source(all_results)},
            "uncertainty": {"type": "Property", "value": uncertainty},
            "lastUpdated": {"type": "Property", "value": "now"},
        }
        await orion.create_entity(agri_soil)


def _cascade_merge(results, depths):
    merged = {f"{d.depth_from}-{d.depth_to}": {} for d in depths}
    for result in sorted(results, key=lambda r: PROVIDER_PRIORITIES.get(r.provider, 0)):
        for horizon in result.horizons:
            key = f"{horizon.depth_from}-{horizon.depth_to}"
            if key in merged:
                for attr in ["sand", "silt", "clay", "organic_carbon", "bulk_density",
                             "ph", "cec", "coarse_fragments", "penetration_resistance"]:
                    val = getattr(horizon, attr)
                    if val is not None and attr not in merged[key]:
                        merged[key][attr] = val
    return [Horizon(depth_from=int(k.split("-")[0]), depth_to=int(k.split("-")[1]), **v)
            for k, v in merged.items()]


def _horizon_to_dict(horizon):
    return {
        "depthFrom": horizon.depth_from, "depthTo": horizon.depth_to,
        "sand": horizon.sand, "silt": horizon.silt, "clay": horizon.clay,
        "organicCarbon": horizon.organic_carbon, "bulkDensity": horizon.bulk_density,
        "ph": horizon.ph, "cec": horizon.cec, "coarseFragments": horizon.coarse_fragments,
        "ksatSaturated": horizon.ksat_saturated,
        "availableWaterCapacity": horizon.available_water_capacity,
        "hydrologicGroup": horizon.hydrologic_group,
        "penetrationResistance": horizon.penetration_resistance,
    }


def _primary_source(results):
    if not results:
        return "soilgrids"
    return max(results, key=lambda r: PROVIDER_PRIORITIES.get(r.provider, 0)).provider


def _aggregate_uncertainty(results):
    if not results:
        return 0.5
    return round(sum(r.uncertainty for r in results) / len(results), 2)


async def reap_stuck_jobs(ctx):
    pass


async def shutdown(ctx):
    pass
