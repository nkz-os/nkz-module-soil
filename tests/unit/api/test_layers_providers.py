import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from nkz_soil.api.main import create_app
from nkz_soil.providers.base import ProviderRegistry


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_layers_manifest(client):
    resp = client.get("/v1/soil/layers/manifest")
    assert resp.status_code == 200
    data = resp.json()
    assert "layers" in data
    assert len(data["layers"]) == 6
    layer_ids = [l["id"] for l in data["layers"]]
    assert "soil-hydrologic-group" in layer_ids
    assert "soil-ksat" in layer_ids
    assert "soil-compaction" in layer_ids


def test_provider_health(client):
    resp = client.get("/v1/soil/providers/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert len(data["providers"]) == 8


def test_provider_coverage(client):
    resp = client.get("/v1/soil/providers/coverage?bbox=-2.0,42.0,-1.0,43.0")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    names = [p["name"] for p in data["providers"]]
    assert "lab_analysis" in names
    assert "soilgrids" in names
    assert "idena" in names
