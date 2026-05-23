"""Async PostgreSQL/PostGIS connection pool for soil_module schema."""
from __future__ import annotations
import os
from typing import AsyncIterator
import asyncpg

_POOL: asyncpg.Pool | None = None


def _dsn() -> str:
    dsn = os.environ.get("SOIL_PG_DSN")
    if not dsn:
        raise RuntimeError("SOIL_PG_DSN not set")
    return dsn


async def get_pool() -> asyncpg.Pool:
    global _POOL
    if _POOL is None:
        _POOL = await asyncpg.create_pool(
            dsn=_dsn(),
            min_size=2,
            max_size=10,
            command_timeout=30,
            server_settings={"search_path": "soil_module,public"},
        )
    return _POOL


async def close_pool() -> None:
    global _POOL
    if _POOL is not None:
        await _POOL.close()
        _POOL = None


async def acquire() -> AsyncIterator[asyncpg.Connection]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
