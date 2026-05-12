from datetime import timedelta, datetime
from nkz_soil.models.domain import SoilProperty, DepthInterval, SoilDataResult, ProviderHealth, GeographicScope, Horizon
from nkz_soil.storage.orion import OrionClient


class IotSensorProvider:
    name = "iot_sensor"
    priority = 90
    geographic_scope = GeographicScope(bbox=(-180, -90, 180, 90), countries=["*"])
    update_cadence = timedelta(hours=1)

    SENSOR_CATEGORY_TO_PROPERTY = {
        "soil_ph": SoilProperty.PH,
        "soil_moisture": SoilProperty.AVAILABLE_WATER_CAPACITY,
        "soil_salinity": SoilProperty.CEC,
        "soil_temperature": None,
        "soil_penetrometer": SoilProperty.PENETRATION_RESISTANCE,
    }

    DEVICE_CATEGORIES = list(SENSOR_CATEGORY_TO_PROPERTY.keys())

    def covers(self, geometry: dict) -> bool:
        return True

    async def fetch(self, geometry: dict, properties: list[SoilProperty], depths: list[DepthInterval]) -> SoilDataResult:
        requested_properties = {p.value for p in properties}

        async with OrionClient() as orion:
            devices = await orion.query_entities(
                type="Device",
                category=self.DEVICE_CATEGORIES,
                geometry=geometry,
            )

        if not devices:
            return SoilDataResult(
                provider=self.name, horizons=[], uncertainty=0.05, geometry=geometry,
            )

        horizon_data = {
            "depth_from": depths[0].depth_from,
            "depth_to": depths[-1].depth_to,
        }

        for device in devices:
            category = device.get("category", {}).get("value", "")
            soil_prop = self.SENSOR_CATEGORY_TO_PROPERTY.get(category)
            if soil_prop is None or soil_prop.value not in requested_properties:
                continue
            value = device.get("value", {}).get("value")
            if value is not None:
                horizon_data[soil_prop.value] = float(value)

        horizon = Horizon(**horizon_data)

        return SoilDataResult(
            provider=self.name,
            horizons=[horizon],
            uncertainty=0.05,
            geometry=geometry,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            name=self.name, status="ok", latency_ms=0,
            last_success=datetime.now(), error_count=0, cache_hit_rate=0.0,
        )
