-- migrations/006_lucas_aux_realign.sql
-- Re-align LUCAS 2018 auxiliary table schemas with the real ESDAC CSVs.
-- The original 002 schema was authored from assumed column names that did
-- not match the published dataset. This migration replaces those columns
-- with ones that map 1:1 to the source files. Idempotent re-runs are safe
-- via ADD COLUMN IF NOT EXISTS / DROP COLUMN IF EXISTS.

-- Bulk density: source CSV exposes 4 depth intervals, not fine/total/coarse.
ALTER TABLE soil_module.lucas_bulk_density_2018
    DROP COLUMN IF EXISTS bd_fine_g_cm3,
    DROP COLUMN IF EXISTS bd_total_g_cm3,
    DROP COLUMN IF EXISTS coarse_frag_pct,
    ADD COLUMN IF NOT EXISTS bd_0_10_g_cm3  REAL,
    ADD COLUMN IF NOT EXISTS bd_10_20_g_cm3 REAL,
    ADD COLUMN IF NOT EXISTS bd_20_30_g_cm3 REAL,
    ADD COLUMN IF NOT EXISTS bd_0_20_g_cm3  REAL;

-- Erosion: source CSV is a field-survey with per-process presence flags.
-- We expose the top-level signs + the six process channels as smallint
-- (NULL preserved for "not surveyed"), instead of synthesizing class/severity.
ALTER TABLE soil_module.lucas_erosion_2018
    DROP COLUMN IF EXISTS erosion_class,
    DROP COLUMN IF EXISTS severity_score,
    ADD COLUMN IF NOT EXISTS signs_observed SMALLINT,
    ADD COLUMN IF NOT EXISTS sheet  SMALLINT,
    ADD COLUMN IF NOT EXISTS rill   SMALLINT,
    ADD COLUMN IF NOT EXISTS gully  SMALLINT,
    ADD COLUMN IF NOT EXISTS mass   SMALLINT,
    ADD COLUMN IF NOT EXISTS dep    SMALLINT,
    ADD COLUMN IF NOT EXISTS wind   SMALLINT;

-- Organic horizon: source CSV captures cultivation + 5 cardinal-direction
-- depth probes and whether each reaches 40 cm. We materialize the mean
-- observed depth (cm) plus the cultivated flag and "taken sample" flag.
ALTER TABLE soil_module.lucas_organic_2018
    DROP COLUMN IF EXISTS horizon_depth_cm,
    DROP COLUMN IF EXISTS horizon_oc_g_kg,
    DROP COLUMN IF EXISTS horizon_n_g_kg,
    ADD COLUMN IF NOT EXISTS cultivated         SMALLINT,
    ADD COLUMN IF NOT EXISTS depth_mean_cm      REAL,
    ADD COLUMN IF NOT EXISTS reaches_40cm_any   SMALLINT,
    ADD COLUMN IF NOT EXISTS sample_taken       SMALLINT;
