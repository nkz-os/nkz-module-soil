"""Apply SQL migrations in order and trigger bulk loaders from MinIO raw bucket.

Idempotent: re-running is safe.
"""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
import asyncpg
import boto3

from nkz_soil.ingest.lucas_loader import load_lucas_topsoil
from nkz_soil.ingest.lucas_aux_loader import (
    load_lucas_bulk_density, load_lucas_erosion, load_lucas_organic,
)
from nkz_soil.ingest.esdb_raster_loader import catalog_esdb_rasters

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
RAW_BUCKET = os.environ.get("MINIO_RAW_BUCKET", "nekazari-soil-raw")


async def _apply_migrations():
    conn = await asyncpg.connect(os.environ["SOIL_PG_DSN"])
    try:
        for m in sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")):
            print(f"[migrate] applying {m.name}", flush=True)
            await conn.execute(m.read_text())
    finally:
        await conn.close()


def _download(s3, key: str, local: Path) -> Path:
    local.parent.mkdir(parents=True, exist_ok=True)
    s3.download_file(RAW_BUCKET, key, str(local))
    return local


async def _bulk_load():
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )
    tmp = Path("/tmp/lucas")
    topsoil = _download(s3, "lucas/LUCAS-SOIL-2018.csv", tmp / "LUCAS-SOIL-2018.csv")
    print(f"[load] topsoil rows = {await load_lucas_topsoil(topsoil)}", flush=True)
    print(f"[load] bd     rows = {await load_lucas_bulk_density(_download(s3, 'lucas/BulkDensity_2018_final-2.csv', tmp / 'BD.csv'))}", flush=True)
    print(f"[load] erosion rows = {await load_lucas_erosion(_download(s3, 'lucas/LUCAS2018_EROSION.csv', tmp / 'ERO.csv'))}", flush=True)
    print(f"[load] organic rows = {await load_lucas_organic(_download(s3, 'lucas/LUCAS2018_ORG.csv', tmp / 'ORG.csv'))}", flush=True)
    # Texture is intentionally not loaded here: LUCAS_Text_All_10032025.csv is
    # not published in the 2018 SOIL bundle. Per-point sand/silt/clay are
    # already on soil_module.lucas_topsoil_2018 and migration 007 backfills
    # lucas_texture_all from it.
    print(f"[catalog] ESDB rasters = {await catalog_esdb_rasters(bucket=RAW_BUCKET, prefix='esdb/')}", flush=True)


async def main():
    await _apply_migrations()
    if os.environ.get("SKIP_BULK_LOAD", "0") == "1":
        print("[load] SKIP_BULK_LOAD=1 — exiting after schema migration", flush=True)
        return
    await _bulk_load()


if __name__ == "__main__":
    asyncio.run(main())
    print("[migrate] done", flush=True)
