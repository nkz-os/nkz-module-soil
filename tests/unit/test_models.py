from nkz_soil.models.ngsi_ld import AgriSoilExtended, GeoProperty, Relationship, TaggedProperty


def test_agri_soil_valid():
    entity = AgriSoilExtended(
        id="urn:ngsi-ld:AgriSoilExtended:test-1",
        location=GeoProperty(value={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}),
        hasAgriParcel=Relationship(object="urn:ngsi-ld:AgriParcel:parcel-1"),
        horizons=TaggedProperty(
            value=[{"depthFrom": 0, "depthTo": 30, "sand": 45, "silt": 35, "clay": 20}],
            provided_by="LUCAS-2018",
            license_id="JRC-LUCAS-2018",
        ),
        parcelVersionId=TaggedProperty(value="v1"),
    )
    out = entity.to_ngsi()
    assert out["type"] == "AgriSoilExtended"
    assert out["horizons"]["providedBy"]["value"] == "LUCAS-2018"
    assert out["horizons"]["license"]["value"] == "JRC-LUCAS-2018"
    assert out["parcelVersionId"]["value"] == "v1"


def test_to_ngsi_omits_context_for_sdk_injection():
    """Producer must NOT pin an @context in the entity body.

    Embedding an unreachable external context (nkz-os.org) made Orion-LD
    return 503 trying to download it, so AgriSoilExtended never persisted.
    The SDK injects the reachable internal platform context when @context
    is absent — so to_ngsi() must omit it entirely.
    """
    entity = AgriSoilExtended(
        id="urn:ngsi-ld:AgriSoilExtended:test-1",
        location=GeoProperty(value={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}),
        hasAgriParcel=Relationship(object="urn:ngsi-ld:AgriParcel:parcel-1"),
        horizons=TaggedProperty(value=[]),
    )
    out = entity.to_ngsi()
    assert "@context" not in out
