import asyncio
import logging

logger = logging.getLogger(__name__)


class SoilModuleLifecycle:
    """Module lifecycle hooks for nkz-module-soil."""

    def __init__(self):
        self.module_id = "soil"

    async def on_install(self, tenant_id: str, config: dict) -> dict:
        bucket_name = f"nkz-soil-{tenant_id}"
        from nkz_soil.storage.minio import get_minio_client

        s3 = get_minio_client()

        max_retries = 3
        for attempt in range(max_retries):
            try:
                await asyncio.to_thread(s3.create_bucket, Bucket=bucket_name)
                logger.info("Created MinIO bucket %s for tenant %s", bucket_name, tenant_id)
                return {"status": "installed", "bucket": bucket_name}
            except s3.exceptions.ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "BucketAlreadyOwnedByYou":
                    logger.info("Bucket %s already exists for tenant %s", bucket_name, tenant_id)
                    return {"status": "installed", "bucket": bucket_name}
                if error_code == "BucketAlreadyExists":
                    logger.warning(
                        "Bucket %s exists but owned by another account", bucket_name
                    )
                    return {"status": "partial", "bucket": bucket_name, "error": "bucket_conflict"}
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(
                        "Bucket creation failed (attempt %d/%d): %s, retrying in %ds",
                        attempt + 1, max_retries, e, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Bucket creation failed after %d attempts: %s", max_retries, e
                    )
            except Exception as e:
                logger.error("Unexpected error creating bucket %s: %s", bucket_name, e)
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                else:
                    return {"status": "partial", "bucket": bucket_name, "error": str(e)}

        return {"status": "partial", "bucket": bucket_name, "error": "max_retries_exceeded"}

    async def on_uninstall(self, tenant_id: str, config: dict) -> dict:
        return {"status": "uninstalled"}

    async def on_config_change(self, tenant_id: str, config: dict) -> dict:
        return {"status": "configured"}


lifecycle = SoilModuleLifecycle()
