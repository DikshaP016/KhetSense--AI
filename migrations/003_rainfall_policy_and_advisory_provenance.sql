-- KhetSense AI: Schema Migration 003 - Rainfall Policy & Advisory Provenance
-- Extends the advisories table with:
-- 1. observed_stress: Raw satellite & soil moisture fusion stress (NDVI + SMAP)
-- 2. rain_forecast_mm: Total precipitation forecasted over the 48-hour window
-- 3. guardrail_triggered: Flag indicating whether rain modified recommendation from dry baseline
-- 4. recommended_action: Agronomic action ('irrigate now', 'irrigate lightly...', 'hold...', etc.)
-- 5. sentinel_scene_date: Timestamp of Sentinel-2 surface reflectance scene
-- 6. smap_obs_date: Timestamp of SMAP SPL3SMP_E soil moisture observation
-- (SQL only: Do not execute against the database until user approval).

ALTER TABLE advisories
ADD COLUMN IF NOT EXISTS observed_stress TEXT NULL;

ALTER TABLE advisories
ADD COLUMN IF NOT EXISTS rain_forecast_mm DOUBLE PRECISION NULL;

ALTER TABLE advisories
ADD COLUMN IF NOT EXISTS guardrail_triggered BOOLEAN NULL DEFAULT FALSE;

ALTER TABLE advisories
ADD COLUMN IF NOT EXISTS recommended_action TEXT NULL;

ALTER TABLE advisories
ADD COLUMN IF NOT EXISTS sentinel_scene_date TIMESTAMPTZ NULL;

ALTER TABLE advisories
ADD COLUMN IF NOT EXISTS smap_obs_date TIMESTAMPTZ NULL;
