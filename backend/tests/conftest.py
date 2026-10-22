"""Pytest configuration — inject mandatory env vars before any module import."""
import os

# Set required env vars before nkz_soil modules are imported.
_TEST_ENV = {
    "MINIO_ENDPOINT": "http://minio-test:9000",
    "MINIO_ACCESS_KEY": "testkey",
    "MINIO_SECRET_KEY": "testsecret",
    "REDIS_URL": "redis://localhost:6379",
    "CONTEXT_URL": "http://context-test/ngsi-ld-context.json",
}
for _k, _v in _TEST_ENV.items():
    os.environ.setdefault(_k, _v)
