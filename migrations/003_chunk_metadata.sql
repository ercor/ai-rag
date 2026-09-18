-- Migration 003: Add page_number and anchor columns to chunks table.
-- Additive, backward-compatible — existing rows get NULL for new columns.

ALTER TABLE chunks ADD COLUMN page_number INT;
ALTER TABLE chunks ADD COLUMN anchor TEXT;
