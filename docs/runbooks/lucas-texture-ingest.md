# Runbook — LUCAS topsoil texture raster ingest (restricted)

The JRC "Topsoil physical properties for Europe" rasters (Ballabio et al. 2016,
LUCAS-derived) are licensed under ESDAC terms that **forbid passing the data to
third parties**. They are therefore:

- **never committed to any repo** (the root `.gitignore` blocks `*.tif*`);
- stored only in a **private** MinIO bucket;
- served only as **derived/aggregated** outputs (Saxton-Rawls hydraulics +
  USDA texture class). Raw clay/sand/silt/bulk-density/coarse-fragments are
  consumed by pedotransfer but suppressed at entity emission (see
  `workers/ingest.py:_emit_raw` and `providers/lucas_texture_raster.py`).

## Prerequisites

- `gdal_translate` (GDAL CLI) and `mc` (MinIO client) configured with an alias
  for the production MinIO (referred to below as `prod`).
- The EU23 source rasters under `clay_sand_etab/*_EU23/`. **Do not upload the
  `_Extra` (wider gap-filled) variants** — only the official EU23 mask is used.

## 1. Convert each EU23 raster to a Cloud-Optimized GeoTIFF

COG tiling lets the provider range-read a single tile instead of pulling the
whole ~250 MB file per query.

```bash
mkdir -p /tmp/cog
for f in Clay_eu23 Sand_eu23 Silt_eu23 Bulk_density_eu23 AWC_eu23 Coarse_frag_eu23 textureUSDA_eu23; do
  src="$(find . -name "$f.tif" -path '*_EU23/*' -o -name "$f.tif" -path '*_23/*' | head -1)"
  gdal_translate -of COG -co COMPRESS=DEFLATE -co BLOCKSIZE=512 "$src" "/tmp/cog/$f.tif"
done
```

## 2. Upload to the PRIVATE bucket/prefix

```bash
mc mb --ignore-existing prod/nekazari-soil-restricted
mc anonymous set none prod/nekazari-soil-restricted        # ensure non-public
mc cp /tmp/cog/*.tif prod/nekazari-soil-restricted/lucas-texture/
```

The catalog loader keys on the exact EU23 filenames
(`clay_eu23.tif`, `sand_eu23.tif`, `silt_eu23.tif`, `bulk_density_eu23.tif`,
`awc_eu23.tif`, `coarse_frag_eu23.tif`, `textureusda_eu23.tif`); keep the names.

## 3. Trigger the catalog

The migrate Job runs `scripts/run_migrations.py`, which calls
`catalog_lucas_texture()` (best-effort; skips cleanly if the bucket is empty).
Re-run it:

```bash
ssh <user>@<server> 'sudo kubectl -n nekazari delete job soil-migrate --ignore-not-found && \
  sudo kubectl -n nekazari apply -f k8s/job-soil-migrate.yaml'
ssh <user>@<server> 'sudo kubectl -n nekazari logs job/soil-migrate | grep "LUCAS texture"'
# expect: [catalog] LUCAS texture = 7
```

## 4. Verify (compliance check)

```bash
# Provider is registered and sees the catalog:
curl -s https://nkz.robotika.cloud/api/v1/soil/providers/health \
  | jq '.providers[] | select(.name=="LUCAS-Texture")'

# After a parcel ingest, the served horizons MUST show null raw fractions
# but populated derived outputs (proof the suppression boundary holds):
curl -s -H "Authorization: Bearer $TOKEN" \
  https://nkz.robotika.cloud/api/v1/soil/parcel/<parcel-id>/summary \
  | jq '.horizons.value[0] | {clay, sand, bulkDensity, availableWaterCapacity, usdaTextureClass}'
# expect clay/sand/bulkDensity = null; availableWaterCapacity + usdaTextureClass populated.
```

If raw clay/sand/silt come back non-null **and** the only contributing source is
LUCAS-Texture, stop — the suppression boundary is not holding and the data must
not be served. Check `_cascade_merge` provenance + `_emit_raw`.
