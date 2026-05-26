from nkz_soil.models.domain import SoilDataResult, Horizon


def test_result_carries_license_priority_redistributable():
    r = SoilDataResult(
        provider="LUCAS-Texture",
        horizons=[Horizon(depth_from=0, depth_to=5, clay=25.0)],
        uncertainty=0.2,
        geometry={"type": "Point", "coordinates": [0, 0]},
        attribution="Ballabio 2016",
        license="JRC-ESDAC-NoRedistribution",
        redistributable=False,
        priority=22,
    )
    assert r.redistributable is False
    assert r.priority == 22
    assert r.license == "JRC-ESDAC-NoRedistribution"


def test_result_defaults_are_redistributable():
    r = SoilDataResult(provider="x", horizons=[], uncertainty=0.1, geometry={})
    assert r.redistributable is True
    assert r.priority == 0
    assert r.license is None
