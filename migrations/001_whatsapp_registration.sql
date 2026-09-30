-- KhetSense AI: Schema Migration 001 - WhatsApp Registration & Spatial Provenance

-- 1. farms: add original WhatsApp pin point geometry
ALTER TABLE farms 
ADD COLUMN IF NOT EXISTS pin geometry(Point, 4326) NULL;

CREATE INDEX IF NOT EXISTS idx_farms_pin ON farms USING gist (pin);

-- 2. farms: add boundary_source with CHECK constraint (default 'manual' for legacy Farm 1)
ALTER TABLE farms 
ADD COLUMN IF NOT EXISTS boundary_source TEXT NOT NULL DEFAULT 'manual' 
CHECK (boundary_source IN ('manual', 'estimated_from_pin', 'drawn_on_map'));

-- 3. farms: add area_source with CHECK constraint (including 'manual' for Farm 1)
ALTER TABLE farms 
ADD COLUMN IF NOT EXISTS area_source TEXT NOT NULL DEFAULT 'default' 
CHECK (area_source IN ('farmer_stated', 'default', 'manual'));

-- 4. Set Farm 1 to explicit manual provenance
UPDATE farms 
SET boundary_source = 'manual', area_source = 'manual' 
WHERE id = 1;

-- 5. farms: relax NOT NULL constraints on location fields for WhatsApp registration
-- (Farmers provide GPS pins; village, district, state are not initially known unless reverse-geocoded)
ALTER TABLE farms ALTER COLUMN village DROP NOT NULL;
ALTER TABLE farms ALTER COLUMN district DROP NOT NULL;
ALTER TABLE farms ALTER COLUMN state DROP NOT NULL;

-- 6. farms: add unique index on mobile_number to prevent duplicate registrations
CREATE UNIQUE INDEX IF NOT EXISTS idx_farms_mobile_number ON farms (mobile_number);

-- 7. registration_sessions: tracks multi-step WhatsApp registration state machine
CREATE TABLE IF NOT EXISTS registration_sessions (
    phone TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    name TEXT,
    crop TEXT,
    acreage_acres DOUBLE PRECISION,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 8. processed_messages: deduplication table to handle Meta webhook retries
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 9. Enable Row Level Security (RLS, no policies) on all three tables
ALTER TABLE farms ENABLE ROW LEVEL SECURITY;
ALTER TABLE registration_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE processed_messages ENABLE ROW LEVEL SECURITY;
