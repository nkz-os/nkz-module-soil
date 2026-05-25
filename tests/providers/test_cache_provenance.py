from nkz_soil.providers.cache import _serialize_result, _deserialize_result
from nkz_soil.models.domain import SoilDataResult, Horizon


def test_roundtrip_preserves_provenance():
    r = SoilDataResult(
        provider="LUCAS-Texture", horizons=[Horizon(depth_from=0, depth_to=5, clay=25.0)],
        uncertainty=0.2, geometry={"type": "Point", "coordinates": [0, 0]},
        attribution="Ballabio 2016", license="JRC-ESDAC-NoRedistribution",
        redistributable=False, priority=22,
    )
    out = _deserialize_result(_serialize_result(r))
    assert out.redistributable is False
    assert out.priority == 22
    assert out.license == "JRC-ESDAC-NoRedistribution"
