class SoilModuleLifecycle:
    """Module lifecycle hooks for nkz-module-soil."""

    def __init__(self):
        self.module_id = "soil"

    async def on_install(self, tenant_id: str, config: dict) -> dict:
        bucket_name = f"nkz-soil-{tenant_id}"
        from nkz_soil.storage.minio import get_minio_client
        s3 = get_minio_client()
        try:
            s3.create_bucket(Bucket=bucket_name)
        except Exception:
            pass
        return {"status": "installed", "bucket": bucket_name}

    async def on_uninstall(self, tenant_id: str, config: dict) -> dict:
        return {"status": "uninstalled"}

    async def on_config_change(self, tenant_id: str, config: dict) -> dict:
        return {"status": "configured"}


lifecycle = SoilModuleLifecycle()
