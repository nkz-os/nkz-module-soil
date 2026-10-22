-- migrations/002_lucas_aux.sql
-- LUCAS auxiliary datasets: bulk density, erosion, organic carbon detail, texture 2025.

CREATE TABLE IF NOT EXISTS soil_module.lucas_bulk_density_2018 (
    point_id     BIGINT PRIMARY KEY REFERENCES soil_module.lucas_topsoil_2018(point_id) ON DELETE CASCADE,
    bd_fine_g_cm3   REAL,
    bd_total_g_cm3  REAL,
    coarse_frag_pct REAL,
    geom         geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS lucas_bd_2018_geom_gix
    ON soil_module.lucas_bulk_density_2018 USING GIST (geom);

CREATE TABLE IF NOT EXISTS soil_module.lucas_erosion_2018 (
    point_id     BIGINT PRIMARY KEY REFERENCES soil_module.lucas_topsoil_2018(point_id) ON DELETE CASCADE,
    erosion_class    VARCHAR(16),
    severity_score   SMALLINT,
    geom         geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS lucas_erosion_2018_geom_gix
    ON soil_module.lucas_erosion_2018 USING GIST (geom);

CREATE TABLE IF NOT EXISTS soil_module.lucas_organic_2018 (
    point_id        BIGINT PRIMARY KEY REFERENCES soil_module.lucas_topsoil_2018(point_id) ON DELETE CASCADE,
    horizon_depth_cm SMALLINT,
    horizon_oc_g_kg  REAL,
    horizon_n_g_kg   REAL,
    geom            geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS lucas_organic_2018_geom_gix
    ON soil_module.lucas_organic_2018 USING GIST (geom);

CREATE TABLE IF NOT EXISTS soil_module.lucas_texture_all (
    point_id     BIGINT PRIMARY KEY,
    survey_year  SMALLINT NOT NULL,
    sand_pct     REAL,
    silt_pct     REAL,
    clay_pct     REAL,
    texture_class VARCHAR(32),
    geom         geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS lucas_texture_geom_gix
    ON soil_module.lucas_texture_all USING GIST (geom);
CREATE INDEX IF NOT EXISTS lucas_texture_year_ix
    ON soil_module.lucas_texture_all (survey_year);

COMMENT ON TABLE soil_module.lucas_bulk_density_2018 IS 'LUCAS 2018 bulk density subset.';
COMMENT ON TABLE soil_module.lucas_erosion_2018 IS 'LUCAS 2018 erosion observations.';
COMMENT ON TABLE soil_module.lucas_organic_2018 IS 'LUCAS 2018 organic horizon details.';
COMMENT ON TABLE soil_module.lucas_texture_all IS 'LUCAS 2018 + 2025 texture survey.';
