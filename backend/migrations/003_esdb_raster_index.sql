-- migrations/003_esdb_raster_index.sql
-- Catalog of ESDB v2 Raster Library 1km×1km objects in MinIO.

CREATE TABLE IF NOT EXISTS soil_module.esdb_raster_index (
    variable     VARCHAR(64) NOT NULL,
    depth_layer  VARCHAR(16) NOT NULL,           -- 'TOP' | 'SUB' | 'ALL'
    storage_uri  TEXT NOT NULL,                  -- s3://nekazari-soil-raw/esdb/<var>/<file>
    bbox         geometry(Polygon, 4326) NOT NULL,
    crs          VARCHAR(16) NOT NULL DEFAULT 'EPSG:3035',
    resolution_m INTEGER NOT NULL DEFAULT 1000,
    citation     TEXT,
    license      VARCHAR(64) NOT NULL DEFAULT 'JRC-ESDB-Raster-Attribution',
    cataloged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (variable, depth_layer)
);
CREATE INDEX IF NOT EXISTS esdb_raster_bbox_gix
    ON soil_module.esdb_raster_index USING GIST (bbox);

COMMENT ON TABLE soil_module.esdb_raster_index IS
  'Catalog of ESDB v2 Raster Library 1km objects in MinIO. License: attribution only (no commercial restriction).';
