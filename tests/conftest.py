import os

# Set required env vars for tests so config.py doesn't crash
os.environ.setdefault("ORION_BASE_URL", "http://localhost:1026")
os.environ.setdefault("MINIO_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-access-key")
os.environ.setdefault("MINIO_SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("CONTEXT_URL", "http://localhost:5000/ngsi-ld-context.json")
