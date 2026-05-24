"""ProviderResult must carry source_tag, license, entitlement, confidence."""
from __future__ import annotations
from nkz_soil.providers.base import ProviderResult


def test_provider_result_carries_full_provenance():
    r = ProviderResult(
        priority=25,
        attributes={"clayContent": 25.0},
        source_tag="LUCAS-2018",
        license="JRC-LUCAS-2018",
        entitlement_required="open",
        confidence_interval={"clayContent": (22.0, 28.0)},
    )
    assert r.source_tag == "LUCAS-2018"
    assert r.license == "JRC-LUCAS-2018"
    assert r.entitlement_required == "open"
    assert r.confidence_interval["clayContent"] == (22.0, 28.0)


def test_provider_result_defaults_to_open_entitlement():
    r = ProviderResult(priority=10, attributes={}, source_tag="X", license="MIT")
    assert r.entitlement_required == "open"
