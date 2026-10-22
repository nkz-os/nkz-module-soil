-- migrations/005_lucas_land_text_widen.sql
-- Widen land_cover/land_use to fit LUCAS LC0_Desc / LU1_Desc human-readable
-- values (e.g. "Cropland", "Grassland with sparse tree cover") that exceed
-- the original VARCHAR(8) code-style limit. Idempotent — re-running is a no-op.
ALTER TABLE soil_module.lucas_topsoil_2018
    ALTER COLUMN land_cover TYPE VARCHAR(64);

ALTER TABLE soil_module.lucas_topsoil_2018
    ALTER COLUMN land_use   TYPE VARCHAR(64);
