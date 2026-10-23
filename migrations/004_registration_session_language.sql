-- KhetSense AI: Schema Migration 004 - Preferred Language Support in Registration Sessions

-- 1. registration_sessions: add preferred_language column with default 'en'
ALTER TABLE registration_sessions 
ADD COLUMN IF NOT EXISTS preferred_language TEXT NOT NULL DEFAULT 'en';

-- 2. farms: ensure default 'en' for preferred_language and populate any NULLs
ALTER TABLE farms 
ALTER COLUMN preferred_language SET DEFAULT 'en';

UPDATE farms 
SET preferred_language = 'en' 
WHERE preferred_language IS NULL;
