"""GET /v1/soil/capabilities returns the parsed capabilities.yaml."""
from __future__ import annotations
from fastapi.testclient import TestClient
from nkz_soil.api.main import app


def test_capabilities_endpoint_returns_module_id():
    with TestClient(app) as client:
        r = client.get("/v1/soil/capabilities")
        assert r.status_code == 200
        body = r.json()
        assert body["moduleId"] == "soil"
        assert body["version"] == "0.2.0"
        assert any(e["entityType"] == "AgriSoilExtended" for e in body["publishes"])


def test_capabilities_endpoint_includes_entitlement_per_attribute():
    with TestClient(app) as client:
        r = client.get("/v1/soil/capabilities")
        agri_soil = next(e for e in r.json()["publishes"] if e["entityType"] == "AgriSoilExtended")
        for attr in agri_soil["attributes"]:
            assert "entitlement" in attr
            assert attr["entitlement"] in {"open", "tier-pro", "esdb-noncommercial"}
