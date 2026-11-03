"""Declared topsoil texture: precedence measured > entered > estimated."""
import copy
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from nkz_soil.api.main import create_app
from nkz_soil.models.domain import Horizon, SoilDataResult
from nkz_soil.pedotransfer.usda_texture import USDA_TEXTURE_CLASSES, usda_texture_class

H_A = {"X-Tenant-ID": "tenant-a", "X-User-ID": "u1", "X-User-Roles": "GestorAgricola"}
H_B = {**H_A, "X-Tenant-ID": "tenant-b"}
URL = "/v1/soil/parcel/p1/declared-texture"
SUMMARY = "/v1/soil/parcel/p1/summary"

PARCEL = "urn:ngsi-ld:AgriParcel:p1"
ENTITY_ID = "urn:ngsi-ld:AgriSoilExtended:p1"


def _entity(source: str | None, data_source: str = "soilgrids") -> dict:
    h = {"depthFrom": 0, "depthTo": 30, "usdaTextureClass": "loam", "sand": 40}
    if source:
        h["usdaTextureSource"] = source
    return {
        "id": ENTITY_ID,
        "type": "AgriSoilExtended",
        "hasAgriParcel": {"type": "Relationship", "object": PARCEL},
        "horizons": {"type": "Property", "value": [h]},
        "dataSource": {"type": "Property", "value": data_source},
    }


class FakeStore:
    """Per-tenant entity store behind a patched OrionClient."""

    def __init__(self):
        self.tenants: dict[str, dict[str, dict]] = {}

    def seed(self, tenant: str, entity: dict):
        self.tenants.setdefault(tenant, {})[entity["id"]] = copy.deepcopy(entity)

    def client(self, tenant_id=None):
        ents = self.tenants.setdefault(tenant_id, {})
        m = AsyncMock()
        m.__aenter__ = AsyncMock(return_value=m)
        m.__aexit__ = AsyncMock(return_value=None)

        async def query(**kw):
            return [copy.deepcopy(e) for e in ents.values() if e["type"] == kw.get("type")]

        async def append(eid, attrs):
            ents[eid].update(copy.deepcopy(attrs))

        async def delete_attr(eid, attr):
            if attr not in ents[eid]:
                raise httpx.HTTPStatusError(
                    "absent", request=MagicMock(), response=MagicMock(status_code=404)
                )
            del ents[eid][attr]

        async def get(eid):
            return copy.deepcopy(ents.get(eid))

        m.query_entities = AsyncMock(side_effect=query)
        m.append_entity_attrs = AsyncMock(side_effect=append)
        m.delete_entity_attr = AsyncMock(side_effect=delete_attr)
        m.get_entity = AsyncMock(side_effect=get)
        m.create_entity = AsyncMock(side_effect=lambda e: ents.__setitem__(e["id"], e))
        return m


@pytest.fixture
def store():
    s = FakeStore()
    with (
        patch("nkz_soil.api.routes.reading.OrionClient", side_effect=s.client),
        patch("nkz_soil.api.routes.writing.OrionClient", side_effect=s.client),
    ):
        yield s


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def _topsoil(client, headers=H_A):
    r = client.get(SUMMARY, headers=headers)
    assert r.status_code == 200
    return r.json()["topsoilTexture"], r.json()["horizons"][0]


def test_declared_beats_estimated(client, store):
    store.seed("tenant-a", _entity("estimated"))
    r = client.put(URL, headers=H_A, json={"usda_texture_class": "clay-loam"})
    assert r.status_code == 200
    assert r.json()["source"] == "entered"
    top, h = _topsoil(client)
    assert top == {"usdaTextureClass": "clay-loam", "source": "entered"}
    assert h["usdaTextureClass"] == "clay-loam"
    assert h["usdaTextureSource"] == "entered"
    # the horizons reader agrees
    hz = client.get("/v1/soil/parcel/p1/horizons", headers=H_A).json()["horizons"][0]
    assert hz["usdaTextureClass"] == "clay-loam"


def test_declaration_is_not_a_sampling_point(client, store):
    store.seed("tenant-a", _entity("estimated"))
    client.put(URL, headers=H_A, json={"usda_texture_class": "sand"})
    assert all(e["type"] == "AgriSoilExtended" for e in store.tenants["tenant-a"].values())


def test_measured_beats_declared(client, store):
    store.seed("tenant-a", _entity("measured", data_source="lab_analysis"))
    assert client.put(URL, headers=H_A, json={"usda_texture_class": "sand"}).status_code == 200
    top, _ = _topsoil(client)
    assert top == {"usdaTextureClass": "loam", "source": "measured"}


def test_legacy_lab_led_horizon_without_source_counts_as_measured(client, store):
    store.seed("tenant-a", _entity(None, data_source="lab_analysis"))
    client.put(URL, headers=H_A, json={"usda_texture_class": "sand"})
    top, _ = _topsoil(client)
    assert top["source"] == "measured"


@pytest.mark.parametrize("bad", ["Loam", "sandy_loam", "", "gravel", None, 3])
def test_invalid_class_is_422(client, store, bad):
    store.seed("tenant-a", _entity("estimated"))
    assert client.put(URL, headers=H_A, json={"usda_texture_class": bad}).status_code == 422
    assert "nkz:declaredUsdaTextureClass" not in store.tenants["tenant-a"][ENTITY_ID]


def test_all_twelve_classes_accepted(client, store):
    store.seed("tenant-a", _entity("estimated"))
    assert len(USDA_TEXTURE_CLASSES) == 12
    for cls in USDA_TEXTURE_CLASSES:
        assert client.put(URL, headers=H_A, json={"usda_texture_class": cls}).status_code == 200


def test_classifier_output_is_in_the_vocabulary():
    # one vocabulary: what ingest emits is what the endpoint accepts
    for sand, silt, clay in [(92, 5, 3), (40, 40, 20), (20, 20, 60), (7, 88, 5), (10, 56, 34)]:
        assert usda_texture_class(sand, silt, clay) in USDA_TEXTURE_CLASSES


def test_delete_restores_estimated_and_is_idempotent(client, store):
    store.seed("tenant-a", _entity("estimated"))
    client.put(URL, headers=H_A, json={"usda_texture_class": "clay"})
    assert client.delete(URL, headers=H_A).status_code == 204
    top, _ = _topsoil(client)
    assert top == {"usdaTextureClass": "loam", "source": "estimated"}
    assert client.delete(URL, headers=H_A).status_code == 204


def test_unknown_parcel_is_404(client, store):
    assert client.put(URL, headers=H_A, json={"usda_texture_class": "loam"}).status_code == 404
    assert client.delete(URL, headers=H_A).status_code == 404


def test_tenant_isolation(client, store):
    store.seed("tenant-a", _entity("estimated"))
    store.seed("tenant-b", _entity("estimated"))
    client.put(URL, headers=H_A, json={"usda_texture_class": "clay"})
    top_b, _ = _topsoil(client, H_B)
    assert top_b == {"usdaTextureClass": "loam", "source": "estimated"}
    # tenant-b cannot reach a parcel that only tenant-a has
    store.tenants["tenant-b"].clear()
    assert client.put(URL, headers=H_B, json={"usda_texture_class": "sand"}).status_code == 404


def test_tenant_comes_from_identity_not_body(client, store):
    store.seed("tenant-a", _entity("estimated"))
    store.seed("tenant-b", _entity("estimated"))
    client.put(URL, headers=H_A, json={"usda_texture_class": "clay", "tenant_id": "tenant-b"})
    assert "nkz:declaredUsdaTextureClass" not in store.tenants["tenant-b"][ENTITY_ID]


def test_full_iri_form_is_read(client, store):
    e = _entity("estimated")
    e["https://nkz-os.org/ns/declaredUsdaTextureClass"] = {"type": "Property", "value": "silt"}
    store.seed("tenant-a", e)
    top, _ = _topsoil(client)
    assert top == {"usdaTextureClass": "silt", "source": "entered"}


@pytest.mark.asyncio
async def test_reingest_does_not_overwrite_declared(client, store):
    from nkz_soil.workers.ingest import ingest_parcel

    store.seed("tenant-a", _entity("estimated"))
    client.put(URL, headers=H_A, json={"usda_texture_class": "sandy-clay"})

    provider = MagicMock()
    provider.name = "soilgrids"
    provider.priority = 10
    provider.covers.return_value = True
    provider.fetch = AsyncMock(return_value=SoilDataResult(
        provider="soilgrids",
        horizons=[Horizon(depth_from=0, depth_to=5, sand=40, silt=40, clay=20, organic_carbon=1.0)],
        uncertainty=0.2, geometry={}, license="x",
    ))
    cb = AsyncMock()
    cb.is_open = AsyncMock(return_value=False)
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    registry = MagicMock()
    registry.get_all.return_value = [provider]
    ctx = {"registry": registry, "circuit_breaker": cb, "cache": cache}
    with (
        patch("nkz_soil.workers.ingest.OrionClient", side_effect=store.client),
        patch("nkz_soil.workers.ingest.invalidate_parcel", AsyncMock()),
    ):
        out = await ingest_parcel(ctx, "p1", "tenant-a", {"type": "Point", "coordinates": [0, 0]}, "v1")
    assert out["status"] == "ingested"
    stored = store.tenants["tenant-a"][ENTITY_ID]
    # ingest rewrote the estimate ...
    assert stored["horizons"]["value"][0]["usdaTextureSource"] == "estimated"
    # ... and the declaration survived and still wins
    assert stored["nkz:declaredUsdaTextureClass"]["value"] == "sandy-clay"
    top, _ = _topsoil(client)
    assert top == {"usdaTextureClass": "sandy-clay", "source": "entered"}


def test_ingest_marks_lab_texture_measured():
    from nkz_soil.models.domain import DepthInterval
    from nkz_soil.workers.ingest import _apply_pedotransfer, _cascade_merge, _horizon_to_dict

    def res(name, prio):
        return SoilDataResult(
            provider=name,
            horizons=[Horizon(depth_from=0, depth_to=5, sand=40, silt=40, clay=20)],
            uncertainty=0.1, geometry={}, license=name, priority=prio,
        )

    for results, expected in [
        ([res("lab_analysis", 100), res("soilgrids", 10)], "measured"),
        ([res("soilgrids", 10)], "estimated"),
    ]:
        h = _apply_pedotransfer(_cascade_merge(results, [DepthInterval(0, 5)]))[0]
        assert _horizon_to_dict(h)["usdaTextureSource"] == expected


def test_written_and_deleted_attribute_is_the_nkz_term(client, store):
    store.seed("tenant-a", _entity("estimated"))
    client.put(URL, headers=H_A, json={"usda_texture_class": "loam"})
    assert list(store.tenants["tenant-a"][ENTITY_ID]).count("nkz:declaredUsdaTextureClass") == 1
    assert "declaredUsdaTextureClass" not in store.tenants["tenant-a"][ENTITY_ID]
    assert client.delete(URL, headers=H_A).status_code == 204
    # the fake raises 404 for a name that is not present, so a 204 with the key gone
    # proves DELETE targeted the same attribute
    assert "nkz:declaredUsdaTextureClass" not in store.tenants["tenant-a"][ENTITY_ID]


@pytest.mark.asyncio
async def test_sdk_delete_path_carries_the_prefixed_term():
    from nkz_platform_sdk.orion import OrionClient as SdkOrion

    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(204)

    c = SdkOrion("tenant-a", base_url="http://orion", context_url="http://ctx")
    c._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await c.delete_entity_attr(ENTITY_ID, "nkz:declaredUsdaTextureClass")
    assert seen[0].endswith("/attrs/nkz%3AdeclaredUsdaTextureClass")
