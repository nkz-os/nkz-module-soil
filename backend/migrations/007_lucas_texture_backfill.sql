-- migrations/007_lucas_texture_backfill.sql
-- Backfill soil_module.lucas_texture_all from LUCAS 2018 topsoil. The 2018
-- bundle ships sand/silt/clay on the main topsoil CSV (not as a separate
-- texture file), so we materialize them in the dedicated texture table for
-- multi-year reads. When the 2025 texture release lands a separate loader
-- will append rows with survey_year=2025.
INSERT INTO soil_module.lucas_texture_all
    (point_id, survey_year, sand_pct, silt_pct, clay_pct, texture_class, geom)
SELECT
    point_id,
    survey_year,
    sand_pct,
    silt_pct,
    clay_pct,
    NULL AS texture_class,
    geom
FROM soil_module.lucas_topsoil_2018
WHERE sand_pct IS NOT NULL
   OR silt_pct IS NOT NULL
   OR clay_pct IS NOT NULL
ON CONFLICT (point_id) DO UPDATE SET
    survey_year   = EXCLUDED.survey_year,
    sand_pct      = EXCLUDED.sand_pct,
    silt_pct      = EXCLUDED.silt_pct,
    clay_pct      = EXCLUDED.clay_pct,
    texture_class = EXCLUDED.texture_class,
    geom          = EXCLUDED.geom;
