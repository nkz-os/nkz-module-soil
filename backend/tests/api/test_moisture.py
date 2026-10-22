"""Unit tests for SMI fetching helpers and the /parcel/{id}/moisture endpoint."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ── _extract_eoproduct_scalar ──────────────────────────────────────────────


def test_extract_scalar_from_property_dict():
    from nkz_soil.storage.orion import _extract_eoproduct_scalar

    entity = {"sarMoisture": {"type": "Property", "value": 0.72}}
    assert _extract_eoproduct_scalar(entity, "sarMoisture") == pytest.approx(0.72)


def test_extract_scalar_from_flat_value():
    from nkz_soil.storage.orion import _extract_eoproduct_scalar

    entity = {"sarMoisture": 0.55}
    assert _extract_eoproduct_scalar(entity, "sarMoisture") == pytest.approx(0.55)


def test_extract_scalar_missing_attr():
    from nkz_soil.storage.orion import _extract_eoproduct_scalar

    entity = {"ndvi": 0.6}
    assert _extract_eoproduct_scalar(entity, "sarMoisture") is None


def test_extract_scalar_none_value():
    from nkz_soil.storage.orion import _extract_eoproduct_scalar

    entity = {"sarMoisture": {"type": "Property", "value": None}}
    assert _extract_eoproduct_scalar(entity, "sarMoisture") is None


def test_extract_scalar_non_numeric():
    from nkz_soil.storage.orion import _extract_eoproduct_scalar

    entity = {"sarMoisture": "not-a-number"}
    assert _extract_eoproduct_scalar(entity, "sarMoisture") is None


# ── fetch_parcel_smi ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_parcel_smi_returns_latest():
    from nkz_soil.storage.orion import fetch_parcel_smi

    entities = [
        {
            "id": "urn:ngsi-ld:EOProduct:tenant:1",
            "sarMoisture": {"type": "Property", "value": 0.60},
            "sensingDate": "2026-06-18",
            "hasAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:p1"},
        },
        {
            "id": "urn:ngsi-ld:EOProduct:tenant:2",
            "sarMoisture": {"type": "Property", "value": 0.72},
            "sensingDate": "2026-06-20",
            "hasAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:p1"},
        },
    ]

    mock_client = AsyncMock()
    mock_client.query_entities = AsyncMock(return_value=entities)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("nkz_soil.storage.orion.OrionClient", return_value=mock_client):
        result = await fetch_parcel_smi("p1", "testtenant")

    assert result is not None
    smi, sensing_date = result
    assert smi == pytest.approx(0.72)
    assert sensing_date == "2026-06-20"


@pytest.mark.asyncio
async def test_fetch_parcel_smi_no_sar_entities():
    from nkz_soil.storage.orion import fetch_parcel_smi

    entities = [
        {
            "id": "urn:ngsi-ld:EOProduct:tenant:1",
            "ndvi": {"type": "Property", "value": 0.65},
            "sensingDate": "2026-06-20",
        }
    ]

    mock_client = AsyncMock()
    mock_client.query_entities = AsyncMock(return_value=entities)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("nkz_soil.storage.orion.OrionClient", return_value=mock_client):
        result = await fetch_parcel_smi("p1", "testtenant")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_parcel_smi_empty_response():
    from nkz_soil.storage.orion import fetch_parcel_smi

    mock_client = AsyncMock()
    mock_client.query_entities = AsyncMock(return_value=[])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("nkz_soil.storage.orion.OrionClient", return_value=mock_client):
        result = await fetch_parcel_smi("p1", "testtenant")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_parcel_smi_orion_error_returns_none():
    from nkz_soil.storage.orion import fetch_parcel_smi

    mock_client = AsyncMock()
    mock_client.query_entities = AsyncMock(side_effect=RuntimeError("Orion down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("nkz_soil.storage.orion.OrionClient", return_value=mock_client):
        result = await fetch_parcel_smi("p1", "testtenant")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_parcel_smi_urn_parcel_id():
    """Full URN parcel_id must not be double-wrapped."""
    from nkz_soil.storage.orion import fetch_parcel_smi

    mock_client = AsyncMock()
    mock_client.query_entities = AsyncMock(return_value=[])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("nkz_soil.storage.orion.OrionClient", return_value=mock_client):
        await fetch_parcel_smi("urn:ngsi-ld:AgriParcel:t:abc", "t")

    call_kwargs = mock_client.query_entities.call_args
    q_arg = call_kwargs.kwargs.get("q") or call_kwargs.args[1] if call_kwargs.args else None
    # q must contain the URN as-is (no double urn:)
    if q_arg is None and call_kwargs.kwargs:
        q_arg = call_kwargs.kwargs["q"]
    assert "urn:ngsi-ld:AgriParcel:t:abc" in q_arg
    assert "urn:ngsi-ld:AgriParcel:urn:" not in q_arg


# ── /parcel/{id}/moisture endpoint ────────────────────────────────────────


@pytest.mark.asyncio
async def test_moisture_endpoint_available():
    from nkz_soil.api.routes.water_budget import parcel_moisture

    mock_auth = MagicMock()
    mock_auth.tenant_id = "testtenant"

    with patch(
        "nkz_soil.api.routes.water_budget.fetch_parcel_smi",
        new=AsyncMock(return_value=(0.72, "2026-06-20")),
    ):
        resp = await parcel_moisture("parcel123", auth=mock_auth)

    assert resp["available"] is True
    assert resp["smi"] == pytest.approx(0.72)
    assert resp["sensingDate"] == "2026-06-20"
    assert "Sentinel-1" in resp["source"]


@pytest.mark.asyncio
async def test_moisture_endpoint_not_available():
    from nkz_soil.api.routes.water_budget import parcel_moisture

    mock_auth = MagicMock()
    mock_auth.tenant_id = "testtenant"

    with patch(
        "nkz_soil.api.routes.water_budget.fetch_parcel_smi",
        new=AsyncMock(return_value=None),
    ):
        resp = await parcel_moisture("parcel123", auth=mock_auth)

    assert resp["available"] is False
    assert resp["smi"] is None
    assert resp["sensingDate"] is None
