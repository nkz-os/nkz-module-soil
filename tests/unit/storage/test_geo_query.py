"""Geo-queries must be valid NGSI-LD: 'near' only for a Point, GeoJSON coords as-is."""
import json

import pytest
import respx
from httpx import Response
from nkz_soil.storage.orion import OrionClient

POLY = {"type": "Polygon", "coordinates": [[[-2.08, 42.64], [-2.07, 42.64], [-2.07, 42.63], [-2.08, 42.64]]]}


@respx.mock
@pytest.mark.asyncio
async def test_polygon_query_uses_intersects_and_nested_coordinates():
    route = respx.get(url__regex=r".*/ngsi-ld/v1/entities.*").mock(return_value=Response(200, json=[]))
    async with OrionClient("t1") as o:
        await o.query_entities(type="SoilSamplingPoint", geometry=POLY)
    params = route.calls.last.request.url.params
    assert params["georel"] == "intersects"
    assert params["geometry"] == "Polygon"
    assert json.loads(params["coordinates"]) == POLY["coordinates"]


@respx.mock
@pytest.mark.asyncio
async def test_point_query_uses_near():
    route = respx.get(url__regex=r".*/ngsi-ld/v1/entities.*").mock(return_value=Response(200, json=[]))
    async with OrionClient("t1") as o:
        await o.query_entities(type="Device", geometry={"type": "Point", "coordinates": [-2.07, 42.64]})
    params = route.calls.last.request.url.params
    assert params["georel"] == "near;maxDistance=50"
    assert json.loads(params["coordinates"]) == [-2.07, 42.64]


def test_esdb_never_maps_organic_carbon_class_codes():
    from nkz_soil.providers import esdb_raster

    assert "OC" not in esdb_raster._VAR_TO_HORIZON
