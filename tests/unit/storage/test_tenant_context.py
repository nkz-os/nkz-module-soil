from nkz_soil.storage import orion as O


def test_default_tenant_is_none():
    assert O.current_tenant() is None


def test_set_and_get_tenant():
    token = O.set_current_tenant("tenant-abc")
    try:
        assert O.current_tenant() == "tenant-abc"
    finally:
        O._TENANT.reset(token)
