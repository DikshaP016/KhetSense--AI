-- KhetSense AI: Schema Migration 006 - Machine Learning Shadow-Mode Evaluation Table
--
-- PURPOSE:
-- 1. Support non-blocking shadow evaluation of machine learning crop-water-stress models (Random Forest, Logistic Regression)
--    alongside the existing production rule engine and rainfall guardrails.
-- 2. Log full multi-sensor inference snapshots (Sentinel-2, SMAP, ERA5-Land/Weather) without altering the advisories table.
-- 3. Capture prediction probabilities, decision thresholds, rule-versus-ML disagreement, and inference latency for offline telemetry.
--
-- IMPORTANT SAFETY NOTICE:
-- This migration script is idempotent (using IF NOT EXISTS).
-- DO NOT execute this migration against the live Supabase database until explicitly authorized in Phase 5 deployment.
-- This file serves as the definitive schema contract for shadow-mode telemetry.

CREATE TABLE IF NOT EXISTS ml_shadow_advisories (
    id BIGSERIAL PRIMARY KEY,
    farm_id BIGINT NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    advisory_id BIGINT REFERENCES advisories(id) ON DELETE SET NULL,
    crop_name VARCHAR(64) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Active Rule Engine Outputs (Current Production Authority)
    rule_observed_stress VARCHAR(32) NOT NULL,
    rule_recommended_action VARCHAR(64) NOT NULL,
    rule_guardrail_triggered BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Candidate ML Model 1: Random Forest Classifier (Calibrated Severe Threshold T=0.33)
    rf_predicted_class VARCHAR(32),
    rf_prob_no_stress DOUBLE PRECISION,
    rf_prob_mild_stress DOUBLE PRECISION,
    rf_prob_severe_stress DOUBLE PRECISION,
    rf_model_version VARCHAR(64),
    
    -- Candidate ML Model 2: Regularized Logistic Regression (Balanced Multi-Class)
    lr_predicted_class VARCHAR(32),
    lr_prob_no_stress DOUBLE PRECISION,
    lr_prob_mild_stress DOUBLE PRECISION,
    lr_prob_severe_stress DOUBLE PRECISION,
    lr_model_version VARCHAR(64),
    
    -- Multi-Sensor Feature Snapshot at Inference Time
    feat_s2_ndvi DOUBLE PRECISION NULL,
    feat_s2_ndwi DOUBLE PRECISION NULL,
    feat_s2_ndre DOUBLE PRECISION NULL,
    feat_s2_msavi DOUBLE PRECISION NULL,
    feat_smap_sm_pct DOUBLE PRECISION NULL,
    feat_era5_precip_season_mm DOUBLE PRECISION NULL,
    feat_era5_temp_mean_c DOUBLE PRECISION NULL,
    feat_era5_temp_max_c DOUBLE PRECISION NULL,
    feat_era5_vpd_mean_kpa DOUBLE PRECISION NULL,
    
    -- Execution Diagnostic Flags & Operational Telemetry
    execution_status VARCHAR(64) NOT NULL DEFAULT 'SUCCESS',  -- 'SUCCESS', 'TIMEOUT_EXCEEDED', 'DEPENDENCY_UNAVAILABLE', 'PERSISTENCE_FAILED'
    is_disagreement BOOLEAN NOT NULL DEFAULT FALSE,           -- True if rule_observed_stress != rf_predicted_class
    severe_disagreement BOOLEAN NOT NULL DEFAULT FALSE,       -- True if either predicted Severe Stress and the other did not
    missing_sensor_flag VARCHAR(128) NULL,                    -- e.g. 'S2_CLOUDY', 'SMAP_LAG_IMPUTED', 'AUX_WEATHER_DEFAULTED'
    inference_latency_ms DOUBLE PRECISION NULL,

    -- Idempotency constraint: exactly one shadow record per advisory assessment
    CONSTRAINT uq_ml_shadow_advisory_id UNIQUE (advisory_id)
);

-- Indices for high-speed offline telemetry aggregation
CREATE INDEX IF NOT EXISTS idx_ml_shadow_farm_created ON ml_shadow_advisories(farm_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ml_shadow_advisory_id ON ml_shadow_advisories(advisory_id);
CREATE INDEX IF NOT EXISTS idx_ml_shadow_crop ON ml_shadow_advisories(crop_name);
CREATE INDEX IF NOT EXISTS idx_ml_shadow_disagreement ON ml_shadow_advisories(is_disagreement, severe_disagreement);
CREATE INDEX IF NOT EXISTS idx_ml_shadow_rf_version ON ml_shadow_advisories(rf_model_version);

-- Documentation metadata
COMMENT ON TABLE ml_shadow_advisories IS 'Offline shadow-mode ML telemetry tracking model predictions alongside rule-based production advisories';
COMMENT ON COLUMN ml_shadow_advisories.rule_observed_stress IS 'Ground-truth production stress assessment from rule engine (NDVI + SMAP fusion)';
COMMENT ON COLUMN ml_shadow_advisories.rf_predicted_class IS 'Random Forest prediction under calibrated severe threshold T=0.33';
COMMENT ON COLUMN ml_shadow_advisories.lr_predicted_class IS 'Regularized multinomial logistic regression prediction';
COMMENT ON COLUMN ml_shadow_advisories.is_disagreement IS 'Flag indicating active rule engine and primary candidate ML model produced divergent classifications';
COMMENT ON COLUMN ml_shadow_advisories.severe_disagreement IS 'Flag indicating divergent classification specifically on the Severe Stress class';
COMMENT ON COLUMN ml_shadow_advisories.missing_sensor_flag IS 'Explicit record of missing or cloud-masked sensor inputs at runtime';
COMMENT ON COLUMN ml_shadow_advisories.inference_latency_ms IS 'Wall-clock execution time for ML feature transformation and inference in milliseconds';
