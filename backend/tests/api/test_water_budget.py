"""Tests for water budget API endpoint."""
import pytest


def test_get_value():
    from nkz_soil.api.routes.water_budget import _get_value

    entity = {"fieldCapacity": {"type": "Property", "value": 0.32}}
    assert _get_value(entity, "fieldCapacity") == 0.32
    assert _get_value(entity, "nonexistent") is None


def test_get_value_with_relationship():
    from nkz_soil.api.routes.water_budget import _get_value

    entity = {
        "hasAgriParcel": {
            "type": "Relationship",
            "object": "urn:ngsi-ld:AgriParcel:abc",
        }
    }
    assert _get_value(entity, "hasAgriParcel") == "urn:ngsi-ld:AgriParcel:abc"
