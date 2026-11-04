"""Every soil reader accepts the new AgriSoilSample next to the legacy SoilSamplingPoint
and answers in the legacy units (cm, %, MPa, ph, snake_case methods)."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from nkz_soil.api.main import create_app
from nkz_soil.models.agri_soil_sample import to_entity
from nkz_soil.util.ngsi import horizons_of

HEADERS = {"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"}
PARCEL_URN = "urn:ngsi-ld:AgriParcel:parcel-1"
PARCEL = {"id": PARCEL_URN, "type": "AgriParcel", "location": {"type": "GeoProperty", "value": {
    "type": "Polygon", "coordinates": [[[-1.7, 42.7], [-1.5, 42.7], [-1.5, 42.9], [-1.7, 42.9], [-1.7, 42.7]]]}}}
BOTH = {"SoilSamplingPoint", "AgriSoilSample"}


def _sample(**over):
    row = {"lat": 42.8, "lon": -1.6, "depth_from": 0, "depth_to": 30, "parcel_id": PARCEL_URN,
           "sampling_date": "2026-09-01", "laboratory_reference": "LAB-9"}
    row.update(over)
    e = to_entity("tenant1", row)
    e.pop("@context")
    return e


LEGACY = {
    "id": "urn:ngsi-ld:SoilSamplingPoint:a", "type": "SoilSamplingPoint",
    "location": {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [-1.6, 42.8]}},
    "samplingDate": {"type": "Property", "value": "2024-10-01"},
    "horizons": {"type": "Property", "value": {"depthFrom": 0, "depthTo": 30, "ph": 8.0}},
    "hasAgriParcel": {"type": "Relationship", "object": PARCEL_URN},
}
TOP = _sample(sand=40, silt=35, clay=25, ph=7.8, phosphorus_available=14.0, phosphorus_method="olsen")
SUB = _sample(depth_from=30, depth_to=60, sand=30, silt=40, clay=30)
PENETRO = _sample(sampling_date="2026-08-15", laboratory_reference=None, penetration_resistance=2.5)


def _types(type_arg):
    return set(type_arg.split(","))


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def reading_orion():
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    with patch("nkz_soil.api.routes.reading.OrionClient", return_value=mock):
        yield mock


def test_horizons_of_reads_agri_soil_sample_in_api_units():
    (h,) = horizons_of(TOP)
    assert h == {"depthFrom": 0, "depthTo": 30, "sand": 40, "silt": 35, "clay": 25, "ph": 7.8,
                 "phosphorusAvailable": 14, "phosphorusMethod": "olsen"}


def test_lab_analyses_merges_both_types(client, reading_orion):
    async def query(type, q=None, geometry=None, **_):
        assert _types(type) == BOTH
        return [LEGACY, TOP, SUB, PENETRO] if not geometry else [TOP, LEGACY]
    reading_orion.query_entities = AsyncMock(side_effect=query)
    reading_orion.get_entity = AsyncMock(return_value=PARCEL)
    body = client.get("/v1/soil/parcel/parcel-1/lab-analyses", headers=HEADERS).json()
    analyses = body["analyses"]
    assert [a["samplingDate"] for a in analyses] == ["2026-09-01", "2024-10-01"]  # newest first, penetrometer out
    new = analyses[0]
    assert new["id"] == TOP["id"] and new["linkedBy"] == "hasAgriParcel" and new["laboratoryReference"] == "LAB-9"
    assert [h["depthFrom"] for h in new["horizons"]] == [0, 30]


def test_depths_regroup_into_one_analysis(client, reading_orion):
    async def query(type, q=None, geometry=None, **_):
        return [] if geometry else [SUB, TOP]
    reading_orion.query_entities = AsyncMock(side_effect=query)
    reading_orion.get_entity = AsyncMock(return_value=PARCEL)
    (a,) = client.get("/v1/soil/parcel/parcel-1/lab-analyses", headers=HEADERS).json()["analyses"]
    assert len(a["horizons"]) == 2 and a["horizons"][0]["sand"] == 40 and a["horizons"][0]["ph"] == 7.8


def test_new_samples_found_only_by_geometry_are_kept(client, reading_orion):
    unlinked = _sample(parcel_id=None, sand=50, silt=30, clay=20)
    async def query(type, q=None, geometry=None, **_):
        return [unlinked] if geometry else []
    reading_orion.query_entities = AsyncMock(side_effect=query)
    reading_orion.get_entity = AsyncMock(return_value=PARCEL)
    (a,) = client.get("/v1/soil/parcel/parcel-1/lab-analyses", headers=HEADERS).json()["analyses"]
    assert a["linkedBy"] == "geometry"


def test_penetrometer_reads_agri_soil_sample(client, reading_orion):
    async def query(type, q=None, geometry=None, **_):
        assert _types(type) == BOTH
        return [PENETRO]
    reading_orion.query_entities = AsyncMock(side_effect=query)
    (p,) = client.get("/v1/soil/penetrometer/parcel-1", headers=HEADERS).json()["points"]
    assert p["resistance"] == 2.5 and p["date"] == "2026-08-15"  # Pa back to MPa
    assert (p["depthFrom"], p["depthTo"], p["lat"], p["lon"]) == (0, 30, 42.8, -1.6)


def test_lab_provider_reads_both_types():
    from nkz_soil.providers.lab_analysis import LabAnalysisProvider
    from nkz_soil.storage import orion as orion_mod
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    seen = []

    async def query(type, geometry=None, **_):
        seen.append(type)
        return [TOP]
    mock.query_entities = AsyncMock(side_effect=query)
    import asyncio
    with patch("nkz_soil.providers.lab_analysis.OrionClient", return_value=mock), \
            patch.object(orion_mod, "current_tenant", return_value="tenant1"):
        res = asyncio.run(LabAnalysisProvider().fetch(PARCEL["location"]["value"], [], []))
    assert _types(seen[0]) == BOTH
    (h,) = res.horizons
    assert (h.sand, h.clay, h.ph, h.depth_to) == (40, 25, 7.8, 30)


def test_zonal_reads_both_types():
    import asyncio

    from nkz_soil.services import zonal
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    seen = []

    async def query(type, geometry=None, **_):
        seen.append(type)
        return [TOP]
    mock.query_entities = AsyncMock(side_effect=query)
    with patch("nkz_soil.services.zonal.OrionClient", return_value=mock):
        points = asyncio.run(zonal._sampling_points_in_zone("tenant1", PARCEL["location"]["value"]))
    assert _types(seen[0]) == BOTH and points == [TOP]
    assert zonal._lab_values(points, (0, 30))


def test_rasterize_reads_both_types(client):
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    pts = [_sample(lat=42.8 + i * 0.001, penetration_resistance=1.0 + i) for i in range(3)]
    seen = []

    async def query(type, q=None, **_):
        seen.append(type)
        return pts
    mock.query_entities = AsyncMock(side_effect=query)
    fake = AsyncMock(return_value={"method": "idw", "url": "u", "entity_id": "r"})
    with patch("nkz_soil.api.routes.writing.OrionClient", return_value=mock), \
            patch("nkz_soil.interpolation.raster.generate_raster", fake):
        r = client.post("/v1/soil/parcel/parcel-1/rasterize?property=penetrationResistance&depth=0-30",
                        headers=HEADERS)
    assert r.status_code == 200, r.text
    assert _types(seen[0]) == BOTH
    assert [p["value"] for p in fake.call_args.kwargs["sample_points"]] == [1.0, 2.0, 3.0]  # MPa


def test_penetrometer_depths_never_join_a_lab_analysis(client, reading_orion):
    """Same point and day, no sample codes: lab 0-30 and penetrometer 0-10/10-20 stay apart,
    or FaST's topsoil mean would lose the lab values."""
    lab = _sample(laboratory_reference=None, sand=40, silt=35, clay=25, organic_matter=1.9)
    pr1 = _sample(laboratory_reference=None, depth_from=0, depth_to=10, penetration_resistance=1.5)
    pr2 = _sample(laboratory_reference=None, depth_from=10, depth_to=20, penetration_resistance=2.0)

    async def query(type, q=None, geometry=None, **_):
        return [] if geometry else [pr1, lab, pr2]
    reading_orion.query_entities = AsyncMock(side_effect=query)
    reading_orion.get_entity = AsyncMock(return_value=PARCEL)
    (a,) = client.get("/v1/soil/parcel/parcel-1/lab-analyses", headers=HEADERS).json()["analyses"]
    assert a["id"] == lab["id"] and len(a["horizons"]) == 1 and a["horizons"][0]["sand"] == 40
