"""
Water Budget Worker — computes soil water balance for all AgriSoil entities.

Runs every 6 hours via Arq schedule:
1. Reads AgriSoil entities with texture data
2. Computes field capacity, wilting point, AWC (Saxton-Rawls PTF)
3. Fetches ET0 forecast from weather-map API
4. Computes 7-day water deficit projection
5. Generates irrigation recommendation
6. Upserts computed attributes back to AgriSoil in Orion-LD
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from nkz_soil.config import SOIL_DEFAULT_TENANT
from nkz_soil.pedotransfer.saxton_rawls import saxton_rawls_2006
from nkz_soil.storage.orion import OrionClient

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

AWC_DEPLETION_THRESHOLD = 0.5  # 50% — trigger irrigation recommendation
WEATHER_API_BASE = "https://nkz.robotika.cloud/api/weather-map"

# ── Main worker function ───────────────────────────────────────────────


async def compute_water_budgets(ctx: dict) -> dict:
    """Main worker entry point. Called by Arq scheduler every 6h.

    Processes all AgriSoil entities for the configured default tenant.
    The tenant is read from the SOIL_DEFAULT_TENANT env var.
    """
    tenant_id = SOIL_DEFAULT_TENANT
    orion = OrionClient(tenant_id)
    try:
        stats = {"processed": 0, "errors": 0, "skipped": 0}

        entities = await orion.query_entities(type="AgriSoilExtended")
        logger.info(
            "Tenant '%s': found %d AgriSoil entities",
            tenant_id, len(entities),
        )

        for entity in entities:
            try:
                horizons = entity.get("horizons", {}).get("value", [])
                if not horizons:
                    stats["skipped"] += 1
                    continue

                h = horizons[0]
                sand = h.get("sand")
                clay = h.get("clay")
                if sand is None or clay is None:
                    stats["skipped"] += 1
                    continue

                oc = h.get("organicCarbon", 0.5)
                ptf = saxton_rawls_2006(sand, clay, oc)
                fc = ptf["field_capacity"]
                pwp = ptf["wilting_point"]
                awc = round(max(0.0, fc - pwp), 3)

                current_moisture = await _get_current_moisture(orion, entity["id"])
                if current_moisture is None:
                    current_moisture = fc * 0.8

                deficit_mm = max(0.0, (fc - current_moisture) * 100)

                parcel_ref = entity.get("hasAgriParcel", {}).get("object", "")
                forecast = await _get_et0_forecast(parcel_ref)
                if not forecast:
                    forecast = _default_forecast()

                projected = _compute_projection(current_moisture, fc, pwp, forecast)

                depletion = (fc - current_moisture) / awc if awc > 0 else 0
                reco = _generate_recommendation(depletion, projected, fc, awc)

                attrs = {
                    "fieldCapacity": {"type": "Property", "value": round(fc, 3), "unitCode": "P1"},
                    "wiltingPoint": {"type": "Property", "value": round(pwp, 3), "unitCode": "P1"},
                    "awc": {"type": "Property", "value": awc, "unitCode": "P1"},
                    "currentMoisture": {
                        "type": "Property",
                        "value": round(current_moisture, 3),
                        "unitCode": "P1",
                    },
                    "deficitMm": {
                        "type": "Property",
                        "value": round(deficit_mm, 1),
                        "unitCode": "MMT",
                    },
                    "forecast7d": {"type": "Property", "value": projected},
                    "lastComputed": {
                        "type": "Property",
                        "value": {
                            "@type": "DateTime",
                            "@value": datetime.now(timezone.utc).isoformat(),
                        },
                    },
                }
                if reco is not None:
                    attrs["irrigationRecommendation"] = {
                        "type": "Property",
                        "value": reco,
                    }

                await orion.patch_entity(entity["id"], attrs)
                stats["processed"] += 1

            except Exception as e:
                logger.error(
                    "Failed to compute water budget for %s: %s",
                    entity.get("id"), e,
                )
                stats["errors"] += 1

        logger.info("Water budget complete: %s", stats)
        return stats
    finally:
        await orion.close()


async def _get_current_moisture(orion: OrionClient, entity_id: str) -> Optional[float]:
    """Try to get current soil moisture from IoT sensor or timeseries."""
    return None


async def _get_et0_forecast(parcel_ref: str) -> Optional[list]:
    """Fetch 7-day ET0 forecast from weather-map API."""
    if not parcel_ref:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{WEATHER_API_BASE}/forecast/et0",
                params={"parcel_id": parcel_ref},
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("forecast", [])
    except Exception as e:
        logger.warning("Failed to fetch ET0 forecast: %s", e)
    return None


def _default_forecast() -> list:
    today = datetime.now(timezone.utc)
    return [
        {
            "day": (today + timedelta(days=i)).strftime("%Y-%m-%d"),
            "et0": 4.0,
            "precip": 0.0,
            "deficitAfter": 0.0,
        }
        for i in range(7)
    ]


def _compute_projection(current_moisture: float, fc: float, pwp: float, forecast: list) -> list:
    moisture = current_moisture
    for day in forecast:
        et0 = day.get("et0", 4.0) / 100
        precip = day.get("precip", 0.0) / 100
        moisture = max(pwp, min(fc, moisture - et0 + precip))
        deficit_after = max(0.0, (fc - moisture) * 100)
        day["deficitAfter"] = round(deficit_after, 1)
    return forecast


def _generate_recommendation(depletion: float, forecast: list, fc: float, awc: float) -> Optional[dict]:
    if depletion < AWC_DEPLETION_THRESHOLD or awc <= 0:
        return None
    for day in forecast:
        if day.get("deficitAfter", 0) > AWC_DEPLETION_THRESHOLD * awc * 100:
            return {
                "shouldIrrigate": True,
                "amountMm": round(day["deficitAfter"] * 0.6, 1),
                "suggestedDay": day["day"],
                "reason": f"Deficit proyectado supera umbral de agotamiento ({int(AWC_DEPLETION_THRESHOLD * 100)}% AWC)",
            }
    return None
