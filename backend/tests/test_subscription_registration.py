"""The ingest subscription must be registered as a Subscription, not as an entity.

register_subscription() posted the Subscription document to POST /ngsi-ld/v1/entities
via create_entity(). Orion stores it as an ordinary entity, no notification is ever
wired, and the Orion -> soil ingest webhook never fires. The endpoint reported success.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nkz_soil.api.routes.subscriptions import SUBSCRIPTION_ID, register_subscription
from nkz_soil.storage.orion import OrionClient


class _Auth:
    tenant_id = "montiko"


@pytest.fixture
def orion_cm():
    """Patch OrionClient so `async with OrionClient(...) as orion` yields a mock."""
    orion = MagicMock()
    orion.create_subscription = AsyncMock(return_value="/ngsi-ld/v1/subscriptions/x")
    orion.create_entity = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=orion)
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch("nkz_soil.api.routes.subscriptions.OrionClient", return_value=cm):
        yield orion


@pytest.mark.asyncio
async def test_registers_via_subscriptions_endpoint(orion_cm):
    out = await register_subscription(auth=_Auth())
    orion_cm.create_subscription.assert_awaited_once()
    assert out["status"] == "registered"


@pytest.mark.asyncio
async def test_never_posts_the_subscription_as_an_entity(orion_cm):
    await register_subscription(auth=_Auth())
    orion_cm.create_entity.assert_not_called()


@pytest.mark.asyncio
async def test_subscription_body_carries_no_context(orion_cm):
    """The client sends application/json + Link; an @context in the body is a 400."""
    await register_subscription(auth=_Auth())
    body = orion_cm.create_subscription.await_args[0][0]
    assert "@context" not in body


@pytest.mark.asyncio
async def test_subscription_shape_is_preserved(orion_cm):
    await register_subscription(auth=_Auth())
    body = orion_cm.create_subscription.await_args[0][0]
    assert body["id"] == SUBSCRIPTION_ID
    assert body["type"] == "Subscription"
    assert body["entities"] == [{"type": "AgriParcel"}]
    assert body["watchedAttributes"] == ["location", "dateModified"]
    assert body["notification"]["endpoint"]["uri"].endswith("/webhooks/orion")


@pytest.mark.asyncio
async def test_already_registered_is_idempotent(orion_cm):
    orion_cm.create_subscription.side_effect = RuntimeError("Already exists")
    out = await register_subscription(auth=_Auth())
    assert out["status"] == "already_registered"


def test_client_exposes_create_subscription():
    assert hasattr(OrionClient, "create_subscription")
