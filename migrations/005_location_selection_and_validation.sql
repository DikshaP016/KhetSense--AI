-- KhetSense AI: Schema Migration 005 - Farm Location Selection & Agricultural Validation Support
--
-- PURPOSE:
-- 1. Support multi-step location selection (at farm vs away from farm) and confirmation before registration.
-- 2. Store pending coordinates (pending_lat, pending_lon) in registration_sessions during the AWAITING_LOCATION_CONFIRMATION state.
-- 3. Store agricultural validation status and land-cover classification in the advisories table for auditability.
--
-- IMPORTANT SAFETY NOTICE:
-- This migration script is idempotent (using IF NOT EXISTS).
-- DO NOT apply this migration automatically. Run manually in Supabase SQL Editor when approved.

-- 1. registration_sessions: add pending_lat and pending_lon for location confirmation step
ALTER TABLE registration_sessions 
ADD COLUMN IF NOT EXISTS pending_lat DOUBLE PRECISION NULL;

ALTER TABLE registration_sessions 
ADD COLUMN IF NOT EXISTS pending_lon DOUBLE PRECISION NULL;

-- 2. advisories: add validation_status and land_cover_class for agricultural validation audit trail
ALTER TABLE advisories 
ADD COLUMN IF NOT EXISTS validation_status TEXT NULL DEFAULT 'UNVALIDATED';

ALTER TABLE advisories 
ADD COLUMN IF NOT EXISTS land_cover_class TEXT NULL;

-- 3. Comments for documentation
COMMENT ON COLUMN registration_sessions.pending_lat IS 'Pending latitude awaiting farmer YES/NO confirmation';
COMMENT ON COLUMN registration_sessions.pending_lon IS 'Pending longitude awaiting farmer YES/NO confirmation';
COMMENT ON COLUMN advisories.validation_status IS 'Agricultural validation outcome (SUITABLE_CROPLAND, LIKELY_URBAN, BARREN_OR_UNCERTAIN, INSUFFICIENT_SATELLITE_DATA, INCOMPLETE_AUXILIARY_DATA, UNVALIDATED)';
COMMENT ON COLUMN advisories.land_cover_class IS 'Land cover classification from ESA WorldCover 10m or similar layer';
