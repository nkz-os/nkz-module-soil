-- migrations/001_lucas_topsoil.sql
-- LUCAS 2018 SOIL main table. Idempotent via IF NOT EXISTS.
CREATE SCHEMA IF NOT EXISTS soil_module;

CREATE TABLE IF NOT EXISTS soil_module.lucas_topsoil_2018 (
    point_id       BIGINT PRIMARY KEY,
    survey_year    SMALLINT NOT NULL DEFAULT 2018,
    country_code   CHAR(2) NOT NULL,
    nuts0          CHAR(2),
    nuts1          VARCHAR(4),
    nuts2          VARCHAR(6),
    elevation_m    REAL,
    land_cover     VARCHAR(8),
    land_use       VARCHAR(8),
    ph_h2o         REAL,
    ph_cacl2       REAL,
    ec_ds_m        REAL,
    oc_g_kg        REAL,
    caco3_g_kg     REAL,
    p_mg_kg        REAL,
    n_g_kg         REAL,
    k_mg_kg        REAL,
    sand_pct       REAL,
    silt_pct       REAL,
    clay_pct       REAL,
    coarse_pct     REAL,
    geom           geometry(Point, 4326) NOT NULL,
    ingested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS lucas_topsoil_2018_geom_gix
    ON soil_module.lucas_topsoil_2018 USING GIST (geom);

CREATE INDEX IF NOT EXISTS lucas_topsoil_2018_country_ix
    ON soil_module.lucas_topsoil_2018 (country_code);

COMMENT ON TABLE soil_module.lucas_topsoil_2018 IS
  'LUCAS 2018 SOIL — JRC ESDAC. License: any-purpose, no raw redistribution. Source: ESDAC dataset 129260.';
