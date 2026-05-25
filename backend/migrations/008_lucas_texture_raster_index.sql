-- backend/migrations/008_lucas_texture_raster_index.sql
-- Catalog of JRC "Topsoil physical properties for Europe" (LUCAS-derived)
-- 500 m rasters held in PRIVATE MinIO. License: NO redistribution to third
-- parties (ESDAC terms, Ballabio et al. 2016). These rasters are served only
-- as derived/aggregated outputs (pedotransfer + USDA class); raw fractions are
-- suppressed at entity emission. The catalog stores only an s3:// pointer plus
-- a Europe-extent bbox and citation -- never pixel data.

CREATE TABLE IF NOT EXISTS soil_module.lucas_texture_raster_index (
    variable        VARCHAR(32) NOT NULL,            -- CLAY|SAND|SILT|BULK_DENSITY|AWC|COARSE_FRAGMENTS|USDA_TEXTURE
    storage_uri     TEXT NOT NULL,                   -- s3://nekazari-soil-restricted/lucas-texture/<file>
    bbox            geometry(Polygon, 4326) NOT NULL,
    crs             VARCHAR(16) NOT NULL DEFAULT 'EPSG:3035',
    resolution_m    INTEGER NOT NULL DEFAULT 500,
    nodata          DOUBLE PRECISION,
    redistributable BOOLEAN NOT NULL DEFAULT false,
    citation        TEXT NOT NULL DEFAULT 'Ballabio C., Panagos P., Montanarella L. (2016) Geoderma 261:110-123',
    license         VARCHAR(48) NOT NULL DEFAULT 'JRC-ESDAC-NoRedistribution',
    cataloged_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (variable)
);
CREATE INDEX IF NOT EXISTS lucas_texture_raster_bbox_gix
    ON soil_module.lucas_texture_raster_index USING GIST (bbox);

COMMENT ON TABLE soil_module.lucas_texture_raster_index IS
  'JRC LUCAS topsoil texture rasters in PRIVATE MinIO. redistributable=false: serve only derived/aggregated outputs.';
