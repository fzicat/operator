-- Migration: add NAV (Net Asset Value) table
-- Run this SQL in the Supabase SQL Editor.

-- ==============================================
-- NAV TABLE (daily Net Asset Value from IBKR Flex Query)
-- One row per day. `date` is the primary key so re-imports
-- with overlapping date ranges never create duplicates.
-- ==============================================
CREATE TABLE IF NOT EXISTS nav (
    date DATE PRIMARY KEY,
    cash NUMERIC,
    stock NUMERIC,
    options NUMERIC,
    dividend_accruals NUMERIC,
    interest_accruals NUMERIC,
    total NUMERIC,
    deposits_withdrawals NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Row Level Security: full access for any authenticated user (single-user app)
ALTER TABLE nav ENABLE ROW LEVEL SECURITY;

CREATE POLICY "auth_all_nav" ON nav
    FOR ALL USING (auth.role() = 'authenticated');

-- Index (date is already the primary key, but keep an explicit one for ordering scans)
CREATE INDEX IF NOT EXISTS idx_nav_date ON nav(date);
