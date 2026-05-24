"""GET /v1/soil/capabilities — serve the parsed capabilities.yaml manifest."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import yaml
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/v1/soil", tags=["capabilities"])

# This file lives at backend/src/nkz_soil/api/routes/capabilities.py
# capabilities.yaml lives at the repo root.
# Path traversal: __file__.parents are:
#   parents[0] = routes/
#   parents[1] = api/
#   parents[2] = nkz_soil/
#   parents[3] = src/
#   parents[4] = backend/
#   parents[5] = <repo root>
_CAPABILITIES_PATH = Path(__file__).resolve().parents[5] / "capabilities.yaml"


@lru_cache(maxsize=1)
def _load() -> dict:
    if not _CAPABILITIES_PATH.exists():
        raise FileNotFoundError(f"capabilities.yaml not found at {_CAPABILITIES_PATH}")
    return yaml.safe_load(_CAPABILITIES_PATH.read_text())


@router.get("/capabilities")
async def get_capabilities() -> dict:
    try:
        return _load()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
