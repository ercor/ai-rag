-- Migration 004: Conversations
-- Adds conversation grouping for multi-turn Q&A.
-- Additive only — existing data is untouched.

-- Conversations table
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL DEFAULT 'New Conversation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for listing conversations by most recently updated
CREATE INDEX idx_conversations_updated ON conversations (updated_at DESC);

-- Link answers to conversations (nullable for backward compatibility)
ALTER TABLE answers ADD COLUMN conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE;

-- Index for fetching answers within a conversation, ordered by time
CREATE INDEX idx_answers_conversation ON answers (conversation_id, created_at);
