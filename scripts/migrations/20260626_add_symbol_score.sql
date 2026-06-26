-- Migration: add `score` column to symbol_targets
-- Run this SQL in the Supabase SQL Editor.

-- ==============================================
-- SYMBOL SCORE
-- Per-symbol integer ranking, typically 0-100. Defaults to 0 so existing
-- rows (and any symbol without an explicit score) read as 0.
-- ==============================================
ALTER TABLE symbol_targets
    ADD COLUMN IF NOT EXISTS score INTEGER NOT NULL DEFAULT 0;
