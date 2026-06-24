"""AgriSoilExtended Property must carry providedBy/license/observedAt sub-properties."""
from __future__ import annotations
from nkz_soil.models.ngsi_ld import AgriSoilExtended, TaggedProperty, GeoProperty, Relationship


def test_tagged_property_serializes_with_provenance():
    p = TaggedProperty(
        value=25.0,
        unit_code="P1",
        provided_by="LUCAS-2018",
        license_id="JRC-LUCAS-2018",
        observed_at="2018-05-12T00:00:00Z",
        confidence_interval=(22.0, 28.0),
    )
    out = p.to_ngsi()
    assert out["type"] == "Property"
    assert out["value"] == 25.0
    assert out["unitCode"] == "P1"
    assert out["providedBy"]["value"] == "LUCAS-2018"
    assert out["license"]["value"] == "JRC-LUCAS-2018"
    assert out["observedAt"] == "2018-05-12T00:00:00Z"
    assert out["confidenceInterval"]["value"] == [22.0, 28.0]


def test_agri_soil_extended_body_has_no_pinned_context():
    """The entity body must not pin an @context (the SDK injects the reachable
    internal platform context). Pinning an external context caused Orion 503s."""
    e = AgriSoilExtended(
        id="urn:ngsi-ld:AgriSoilExtended:p-1",
        location=GeoProperty(value={"type": "Point", "coordinates": [0, 0]}),
        hasAgriParcel=Relationship(object="urn:ngsi-ld:AgriParcel:p-1"),
        horizons=TaggedProperty(value=[], provided_by="LUCAS-2018", license_id="JRC-LUCAS-2018"),
    )
    assert "@context" not in e.to_ngsi()
