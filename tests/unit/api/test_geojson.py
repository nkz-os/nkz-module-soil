from nkz_soil.api.geojson import (
    is_allowed_attribute, build_parcel_featurecollection,
)


def _entity(pid, geom, top):
    return {
        "id": f"urn:ngsi-ld:AgriSoilExtended:{pid}",
        "hasAgriParcel": {"object": f"urn:ngsi-ld:AgriParcel:{pid}"},
        "location": {"value": geom},
        "horizons": {"value": [top]},
    }


def test_allowed_attrs_are_derived_only():
    assert is_allowed_attribute("usdaTextureClass")
    assert is_allowed_attribute("availableWaterCapacity")
    assert is_allowed_attribute("hydrologicGroup")
    for raw in ("clay", "sand", "silt", "bulkDensity", "coarseFragments", "organicCarbon"):
        assert not is_allowed_attribute(raw)


def test_build_featurecollection_picks_topsoil_attribute():
    geom = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]}
    fc = build_parcel_featurecollection(
        [_entity("p1", geom, {"depthFrom": 0, "depthTo": 5, "usdaTextureClass": "loam"})],
        "usdaTextureClass",
    )
    assert fc["type"] == "FeatureCollection"
    f = fc["features"][0]
    assert f["geometry"] == geom
    assert f["properties"]["parcelId"] == "p1"
    assert f["properties"]["attribute"] == "usdaTextureClass"
    assert f["properties"]["value"] == "loam"


def test_build_skips_entities_without_geometry_or_value():
    fc = build_parcel_featurecollection(
        [{"id": "x", "horizons": {"value": [{"depthFrom": 0, "depthTo": 5}]}}],
        "availableWaterCapacity",
    )
    assert fc["features"] == []
