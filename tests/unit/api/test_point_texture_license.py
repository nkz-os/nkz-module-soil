"""License-boundary tests for GET /point/texture.

The endpoint triggers the full provider chain and returns texture + derived
hydraulic properties. When the winning provider is non-redistributable
(e.g. JRC LUCAS texture raster, license 'JRC-ESDAC-NoRedistribution'), the
RAW fractions (sand/silt/clay/organicCarbon) MUST be withheld from the
response — only the derived products (usdaTextureClass, Saxton-Rawls
hydraulics, SCS hydrologic group) may be served. This mirrors the worker's
suppression boundary (workers/ingest.py::_emit_raw).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from nkz_soil.api.main import create_app
from nkz_soil.models.domain import Horizon, SoilDataResult

_HEADERS = {"X-Tenant-ID": "tenant1", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"}


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def _registry_with(result: SoilDataResult):
    """Build a mock provider registry whose single provider returns `result`."""
    provider = MagicMock()
    provider.covers.return_value = True
    provider.fetch = AsyncMock(return_value=result)
    registry = MagicMock()
    registry.get_all.return_value = [provider]
    return registry


def _result(*, redistributable: bool, license: str) -> SoilDataResult:
    horizon = Horizon(
        depth_from=0, depth_to=5,
        sand=40.0, silt=40.0, clay=20.0, organic_carbon=1.2,
    )
    return SoilDataResult(
        provider="lucas_texture_raster",
        horizons=[horizon],
        uncertainty=0.1,
        geometry={"type": "Point", "coordinates": [0.0, 0.0]},
        attribution="JRC ESDAC LUCAS texture",
        license=license,
        redistributable=redistributable,
    )


def test_non_redistributable_withholds_raw_fractions(client):
    result = _result(redistributable=False, license="JRC-ESDAC-NoRedistribution")
    with patch("nkz_soil.api.routes.providers._registry", _registry_with(result)):
        resp = client.get("/v1/soil/point/texture?lat=42.0&lon=-1.5", headers=_HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    texture = body["texture"]
    # Raw fractions from a non-redistributable source must NOT be served.
    assert texture["sand"] is None
    assert texture["silt"] is None
    assert texture["clay"] is None
    assert texture["organicCarbon"] is None
    # Derived products are "new works under the license" — always served.
    assert texture["usdaTextureClass"] is not None
    assert body["hydraulic"]["fieldCapacity"] is not None
    assert body["hydraulic"]["saturatedHydraulicConductivity"] is not None
    assert body["hydraulic"]["hydrologicGroup"] is not None
    # License provenance is still surfaced for the caller.
    assert body["source"]["license"] == "JRC-ESDAC-NoRedistribution"


def test_redistributable_serves_raw_fractions(client):
    result = _result(redistributable=True, license="LUCAS-2018-Open")
    with patch("nkz_soil.api.routes.providers._registry", _registry_with(result)):
        resp = client.get("/v1/soil/point/texture?lat=42.0&lon=-1.5", headers=_HEADERS)

    assert resp.status_code == 200
    texture = resp.json()["texture"]
    assert texture["sand"] == 40.0
    assert texture["silt"] == 40.0
    assert texture["clay"] == 20.0
    assert texture["organicCarbon"] == 1.2
    assert texture["usdaTextureClass"] is not None
