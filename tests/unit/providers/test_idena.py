from unittest.mock import AsyncMock, patch

import pytest
from nkz_soil.models.domain import DepthInterval, SoilProperty
from nkz_soil.pedotransfer.usda_texture import usda_texture_class
from nkz_soil.providers.idena import TEXTURE_CLASS_FRACTIONS, IdenaProvider

DEPTHS = [DepthInterval(0, 5), DepthInterval(5, 15), DepthInterval(15, 30),
          DepthInterval(30, 60), DepthInterval(60, 100)]
ALL_PROPS = list(SoilProperty)

PARCEL = {"type": "Polygon", "coordinates": [[
    [-1.6010, 42.8010], [-1.5990, 42.8010], [-1.5990, 42.7990],
    [-1.6010, 42.7990], [-1.6010, 42.8010],
]]}


def _recinto(x0, y0, x1, y1, hs1, geomorf="Laderas de erosión sobre margas, areniscas y limos"):
    """A WFS feature shaped like IDENA's EDAFOL_Pol_Suelos25m (EPSG:4326, lon/lat)."""
    return {
        "type": "Feature",
        "geometry": {"type": "MultiPolygon", "coordinates": [[[
            [x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0],
        ]]]},
        "properties": {
            "GEOMORF1": geomorf,
            "SOILTAXON1": "Fluventic Haploxerept",
            "CLASIF_SC1": "Arcillosa fina, Mixta, Profunda",
            "CLASIF_HS1": hs1,
        },
    }


@pytest.fixture
def provider():
    return IdenaProvider()


def test_provider_metadata(provider):
    assert provider.name == "idena"
    assert provider.priority == 40


def test_covers_geometry(provider):
    geometry = {"type": "Polygon", "coordinates": [[[-1.6, 42.8], [-1.5, 42.8], [-1.5, 42.9], [-1.6, 42.8]]]}
    assert provider.covers(geometry) is True


@pytest.mark.parametrize("label,slug", [
    ("Franco arcillo limosa", "silty-clay-loam"),
    ("Franco arcillosa", "clay-loam"),
    ("Arcillo limosa", "silty-clay"),
    ("Franca", "loam"),
    ("Franco limosa", "silt-loam"),
    ("Franco arenosa", "sandy-loam"),
    ("Arcillosa", "clay"),
    ("Franco arcillo arenosa", "sandy-clay-loam"),
    ("Arenosa franca", "loamy-sand"),
    ("Limosa", "silt"),
])
def test_class_fractions_reclassify_to_the_same_usda_class(label, slug):
    sand, silt, clay = TEXTURE_CLASS_FRACTIONS[label]
    assert sand + silt + clay == pytest.approx(100)
    assert usda_texture_class(sand, silt, clay) == slug


async def _fetch(provider, features, geometry=PARCEL):
    with patch.object(provider, "_get_features", AsyncMock(return_value=features)):
        return await provider.fetch(geometry, ALL_PROPS, DEPTHS)


@pytest.mark.asyncio
async def test_picks_the_recinto_under_the_parcel_not_the_first(provider):
    # First feature is nearby but does not contain the parcel (a water body, say).
    features = [
        _recinto(-1.6100, 42.8100, -1.6050, 42.8150, "Arcillosa"),
        _recinto(-1.6020, 42.7980, -1.5980, 42.8020, "Franco limosa"),
    ]
    result = await _fetch(provider, features)
    top = result.horizons[0]
    assert (top.sand, top.silt, top.clay) == TEXTURE_CLASS_FRACTIONS["Franco limosa"]


@pytest.mark.asyncio
async def test_texture_comes_from_surface_class_not_geomorphology(provider):
    # "areniscas" in the geomorphology used to be read as 90 % sand.
    result = await _fetch(provider, [_recinto(-1.602, 42.798, -1.598, 42.802, "Franco arcillo limosa")])
    top = result.horizons[0]
    assert usda_texture_class(top.sand, top.silt, top.clay) == "silty-clay-loam"


@pytest.mark.asyncio
async def test_only_surface_horizon_and_no_invented_ph_or_carbon(provider):
    result = await _fetch(provider, [_recinto(-1.602, 42.798, -1.598, 42.802, "Franca")])
    depths = [(h.depth_from, h.depth_to) for h in result.horizons]
    assert depths == [(0, 5), (5, 15), (15, 30)]
    for h in result.horizons:
        assert h.ph is None
        assert h.organic_carbon is None


@pytest.mark.asyncio
async def test_no_containing_recinto_yields_no_horizons(provider):
    result = await _fetch(provider, [_recinto(-1.6100, 42.8100, -1.6050, 42.8150, "Franca")])
    assert result.horizons == []


@pytest.mark.asyncio
async def test_unmapped_class_yields_no_horizons(provider):
    result = await _fetch(provider, [_recinto(-1.602, 42.798, -1.598, 42.802, "Esquelética arcillosa")])
    assert result.horizons == []


@pytest.mark.asyncio
async def test_multipolygon_parcel_is_located(provider):
    multi = {"type": "MultiPolygon", "coordinates": [PARCEL["coordinates"]]}
    get = AsyncMock(return_value=[_recinto(-1.602, 42.798, -1.598, 42.802, "Franca")])
    with patch.object(provider, "_get_features", get):
        result = await provider.fetch(multi, ALL_PROPS, DEPTHS)
    lon, lat = get.await_args.args
    assert lon == pytest.approx(-1.6, abs=0.002)
    assert lat == pytest.approx(42.8, abs=0.002)
    assert result.horizons
