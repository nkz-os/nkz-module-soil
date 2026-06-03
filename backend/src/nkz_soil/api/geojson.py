"""Pure helpers to build a parcel-choropleth GeoJSON FeatureCollection from
AgriSoilExtended entities, with a license guard restricting layers to derived
aggregates (never raw fractions)."""
from __future__ import annotations

ALLOWED_LAYER_ATTRS = {
    "usdaTextureClass", "availableWaterCapacity", "fieldCapacity",
    "wiltingPoint", "ksatSaturated", "hydrologicGroup",
    "compactionSusceptibilityScore", "compactionSusceptibilityClass",
}


def is_allowed_attribute(attribute: str) -> bool:
    return attribute in ALLOWED_LAYER_ATTRS


def _parcel_id(entity: dict) -> str:
    ref = entity.get("refAgriParcel", {}).get("object", "")
    if ref:
        return ref.split(":")[-1]
    return entity.get("id", "").split(":")[-1]


def build_parcel_featurecollection(entities: list[dict], attribute: str) -> dict:
    features = []
    for e in entities:
        geom = (e.get("location") or {}).get("value")
        horizons = (e.get("horizons") or {}).get("value") or []
        if not geom or not horizons:
            continue
        value = horizons[0].get(attribute)
        if value is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "parcelId": _parcel_id(e),
                "attribute": attribute,
                "value": value,
            },
        })
    return {"type": "FeatureCollection", "features": features}
