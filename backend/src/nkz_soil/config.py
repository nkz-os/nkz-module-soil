import os

ORION_LD_URL = os.getenv("ORION_LD_URL") or os.getenv(
    "ORION_BASE_URL", "http://orion-ld-service:1026"
)
MINIO_ENDPOINT = os.environ["MINIO_ENDPOINT"]
MINIO_ACCESS_KEY = os.environ["MINIO_ACCESS_KEY"]
MINIO_SECRET_KEY = os.environ["MINIO_SECRET_KEY"]
REDIS_URL = os.environ["REDIS_URL"]
CONTEXT_URL = os.environ["CONTEXT_URL"]
ORION_WEBHOOK_SECRET = os.getenv("ORION_WEBHOOK_SECRET", "")

CACHE_TTL_BASELINE = int(os.environ.get("CACHE_TTL_BASELINE", "31536000"))
CACHE_TTL_REVISABLE = int(os.environ.get("CACHE_TTL_REVISABLE", "2592000"))
INGESTION_BUFFER_M = float(os.environ.get("INGESTION_BUFFER_M", "50.0"))
PROVIDER_RETRY_MAX = int(os.environ.get("PROVIDER_RETRY_MAX", "5"))
PROVIDER_ISOLATE_SECONDS = int(os.environ.get("PROVIDER_ISOLATE_SECONDS", "900"))

# CSV batch upload limits
BATCH_MAX_ROWS = int(os.environ.get("SOIL_BATCH_MAX_ROWS", "500"))
BATCH_MAX_BYTES = int(os.environ.get("SOIL_BATCH_MAX_BYTES", str(2 * 1024 * 1024)))
BATCH_CONCURRENCY = int(os.environ.get("SOIL_BATCH_CONCURRENCY", "15"))
