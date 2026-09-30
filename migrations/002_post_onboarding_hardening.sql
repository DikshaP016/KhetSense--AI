-- KhetSense AI: Schema Migration 002 - Post-Onboarding Security & Normalization Hardening

-- 1. Enable Row Level Security (RLS, no policies) on advisories table
ALTER TABLE advisories ENABLE ROW LEVEL SECURITY;

-- 2. Normalize Farm 1 legacy mobile number to Meta digits format (919999999999)
UPDATE farms 
SET mobile_number = '919999999999' 
WHERE id = 1;
