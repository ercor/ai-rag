# Conversation History Specification

## Purpose

Define the conversation history capability that groups Q&A exchanges into named conversations, persists them to the database, provides CRUD API endpoints, includes prior messages as context in the generation prompt, and exposes a conversation sidebar in the frontend.

## Requirements

### Requirement: Conversation Data Model

The system SHALL define a `Conversation` model with fields: `id` (UUID, primary key), `title` (text, auto-generated from first question), `created_at` (timestamp), `updated_at` (timestamp).

The `answers` table SHALL gain a nullable `conversation_id` foreign key referencing `conversations(id)`. Existing answers without a `conversation_id` MUST remain valid (backward compatible).

#### Scenario: Conversation created

- GIVEN a user creates a new conversation
- WHEN the `POST /v1/conversations` endpoint is called
- THEN a new conversation record is created with a UUID, empty or auto-generated title, and current timestamps

#### Scenario: Answers linked to conversation

- GIVEN an existing conversation with id "conv-123"
- WHEN an answer is created with `conversation_id="conv-123"`
- THEN the answer record's `conversation_id` column is set to "conv-123"

#### Scenario: Answers without conversation

- GIVEN no `conversation_id` is provided in the request
- WHEN an answer is created
- THEN the answer record's `conversation_id` is `NULL`
- AND the answer is still persisted and retrievable

### Requirement: Database Migration

The system SHALL provide a migration that creates the `conversations` table and adds the `conversation_id` column to `answers`.

The migration MUST be additive — it MUST NOT modify or delete existing data. The `conversation_id` column on `answers` MUST be nullable.

#### Scenario: Migration applies cleanly

- GIVEN the existing database schema (chunks, answers, documents tables)
- WHEN the migration runs
- THEN the `conversations` table is created
- AND the `answers` table gains a nullable `conversation_id` UUID column
- AND an index on `answers(conversation_id, created_at)` is created
- AND all existing answers remain intact with `conversation_id=NULL`

#### Scenario: Migration rollback

- GIVEN the migration has been applied
- WHEN the migration is rolled back
- THEN the `conversation_id` column is dropped from `answers`
- AND the `conversations` table is dropped
- AND existing data in `answers` (minus conversation_id) is preserved

### Requirement: ConversationRepository Port

The system SHALL define a `ConversationRepository` port (Protocol) with operations: `create()`, `get_by_id()`, `list()`, `delete()`, `get_answers()`, `update_title()`.

The port MUST be adapter-agnostic — no SQL or PostgreSQL-specific types SHALL appear in the interface.

#### Scenario: Create conversation

- GIVEN a title "Travel Policy Questions"
- WHEN `ConversationRepository.create(title)` is called
- THEN a new conversation is persisted and its full model is returned

#### Scenario: List conversations

- GIVEN 5 conversations exist, ordered by `updated_at` descending
- WHEN `ConversationRepository.list(limit=3, offset=0)` is called
- THEN the 3 most recently updated conversations are returned

#### Scenario: Get conversation by ID

- GIVEN a conversation with id "conv-123" exists
- WHEN `ConversationRepository.get_by_id("conv-123")` is called
- THEN the full conversation model is returned

#### Scenario: Get conversation answers

- GIVEN conversation "conv-123" has 4 answers
- WHEN `ConversationRepository.get_answers("conv-123")` is called
- THEN all 4 answers are returned ordered by `created_at` ascending

#### Scenario: Delete conversation cascades

- GIVEN conversation "conv-123" has 4 answers
- WHEN `ConversationRepository.delete("conv-123")` is called
- THEN the conversation and all its answers are deleted
- AND answers not linked to this conversation are unaffected

### Requirement: PostgreSQL Conversation Repository Adapter

The system SHALL provide a `PgConversationRepository` adapter that implements the `ConversationRepository` port using asyncpg.

The adapter MUST use parameterized queries to prevent SQL injection. Delete operations MUST cascade to linked answers.

#### Scenario: Parameterized queries

- GIVEN a conversation title containing SQL injection attempt: `"; DROP TABLE answers; --`
- WHEN the title is stored via the adapter
- THEN the title is stored as-is (literal string); no SQL injection occurs

#### Scenario: Cascade delete

- GIVEN a conversation with 3 answers
- WHEN the conversation is deleted at the database level
- THEN all 3 linked answers are also deleted (via ON DELETE CASCADE or explicit deletion)

### Requirement: Conversation CRUD API

The system SHALL expose REST API endpoints for conversation management.

Endpoints:
- `POST /v1/conversations` — create new conversation (body: optional `title`)
- `GET /v1/conversations` — list conversations (query params: `limit`, `offset`)
- `GET /v1/conversations/{id}` — get conversation with its answers
- `DELETE /v1/conversations/{id}` — delete conversation and its answers

#### Scenario: Create conversation via API

- GIVEN a POST request to `/v1/conversations` with body `{"title": "My Chat"}`
- WHEN the request is processed
- THEN a 201 response is returned with the conversation object including its UUID

#### Scenario: List conversations via API

- GIVEN 10 conversations exist
- WHEN `GET /v1/conversations?limit=5&offset=0` is called
- THEN a 200 response is returned with 5 conversations ordered by `updated_at` descending

#### Scenario: Get conversation with answers

- GIVEN conversation "conv-123" has 3 answers
- WHEN `GET /v1/conversations/conv-123` is called
- THEN a 200 response is returned with the conversation object and its 3 answers inline

#### Scenario: Delete conversation via API

- GIVEN conversation "conv-123" exists with 2 answers
- WHEN `DELETE /v1/conversations/conv-123` is called
- THEN a 204 response is returned
- AND the conversation and its 2 answers are deleted

#### Scenario: Get non-existent conversation

- GIVEN no conversation with id "fake-id" exists
- WHEN `GET /v1/conversations/fake-id` is called
- THEN a 404 response is returned

### Requirement: Answer Request with Conversation ID

The system SHALL accept an optional `conversation_id` field in the `POST /v1/answers` request body.

When provided, the created answer MUST be linked to the specified conversation. When omitted, the answer is created without a conversation link (backward compatible).

#### Scenario: Answer with conversation ID

- GIVEN a POST request to `/v1/answers` with `{"question": "...", "conversation_id": "conv-123"}`
- WHEN the answer is created
- THEN the answer's `conversation_id` is set to "conv-123"
- AND the conversation's `updated_at` is refreshed

#### Scenario: Answer without conversation ID

- GIVEN a POST request to `/v1/answers` with `{"question": "..."}`
- WHEN the answer is created
- THEN the answer's `conversation_id` is `NULL`
- AND no conversation is affected

#### Scenario: Answer with invalid conversation ID

- GIVEN a POST request with `conversation_id: "non-existent"`
- WHEN the answer is created
- THEN a 400 or 404 error is returned indicating the conversation does not exist

### Requirement: Conversation Context in Prompt

The system SHALL include the last N messages from the conversation history in the generation prompt when a `conversation_id` is provided.

The default N is configurable via `max_conversation_history` (default: 5). History is formatted as alternating Q/A pairs and prepended to the prompt before the current question. The total history SHOULD be limited to approximately 1000 tokens.

#### Scenario: History included in prompt

- GIVEN a conversation with 3 prior Q&A exchanges and `max_conversation_history=5`
- WHEN a new question is asked in this conversation
- THEN the prompt includes all 3 prior exchanges formatted as "Q: ... A: ..." pairs
- AND the current question follows the history

#### Scenario: History truncated to max

- GIVEN a conversation with 10 prior exchanges and `max_conversation_history=5`
- WHEN a new question is asked
- THEN only the last 5 exchanges are included in the prompt
- AND the oldest 5 exchanges are excluded

#### Scenario: No history for new conversation

- GIVEN a conversation with 0 prior exchanges (new conversation)
- WHEN a question is asked
- THEN no history section is included in the prompt
- AND the prompt is identical to the single-query prompt

#### Scenario: No history without conversation ID

- GIVEN no `conversation_id` is provided
- WHEN a question is asked
- THEN no history section is included in the prompt

### Requirement: Auto-Generate Conversation Title

The system SHALL auto-generate a conversation title from the first question when no explicit title is provided.

The title SHOULD be a truncated version of the first question (max 80 characters).

#### Scenario: Auto-title from first question

- GIVEN a new conversation created without a title
- WHEN the first question "What is the travel reimbursement policy for international trips?" is asked
- THEN the conversation title is set to "What is the travel reimbursement policy for international t..." (truncated to 80 chars)

#### Scenario: Explicit title preserved

- GIVEN a new conversation created with title "HR Policies"
- WHEN the first question is asked
- THEN the conversation title remains "HR Policies"

### Requirement: Conversation Configuration

The system SHALL expose conversation settings via environment variables.

Required settings: `max_conversation_history` (int, default: 5).

#### Scenario: Default configuration

- GIVEN no conversation environment variables are set
- WHEN settings are loaded
- THEN `max_conversation_history=5`

#### Scenario: Custom history limit

- GIVEN `MAX_CONVERSATION_HISTORY=10` is set
- WHEN settings are loaded
- THEN `max_conversation_history=10`

### Requirement: Frontend Conversation Sidebar

The system SHALL display a conversation sidebar in the frontend that lists all conversations, allows creating new conversations, switching between conversations, and deleting conversations.

The sidebar MUST persist across page refreshes by fetching conversations from the API. Messages within a conversation MUST persist across page refreshes.

#### Scenario: Sidebar shows conversation list

- GIVEN 5 conversations exist in the database
- WHEN the frontend loads
- THEN the sidebar displays all 5 conversations ordered by most recent first
- AND each entry shows the conversation title and last updated time

#### Scenario: Create new conversation

- GIVEN the user clicks "New Conversation"
- WHEN the button is clicked
- THEN a new conversation is created via the API
- AND the sidebar updates to show the new conversation at the top
- AND the chat area is cleared for the new conversation

#### Scenario: Switch conversation

- GIVEN the user is viewing conversation A
- WHEN the user clicks conversation B in the sidebar
- THEN the chat area loads conversation B's message history from the API
- AND the previous messages from conversation B are displayed

#### Scenario: Delete conversation

- GIVEN the user clicks delete on conversation C
- WHEN the deletion is confirmed
- THEN the conversation is deleted via the API
- AND the sidebar removes conversation C
- AND if the user was viewing C, the chat switches to the most recent remaining conversation or an empty state

#### Scenario: Page refresh preserves state

- GIVEN the user is in the middle of a conversation
- WHEN the page is refreshed
- THEN the conversation sidebar reloads from the API
- AND the current conversation's messages are reloaded
- AND the chat state is restored

### Requirement: Frontend Message Persistence

The system SHALL persist all messages (questions and answers) via the conversation API so they survive page refreshes.

Messages MUST be loaded from the API when a conversation is selected, not from local state alone.

#### Scenario: Messages persist across refresh

- GIVEN a conversation with 3 Q&A exchanges
- WHEN the user refreshes the page
- THEN all 3 exchanges are reloaded from the API and displayed

#### Scenario: New messages appear immediately

- GIVEN the user asks a new question
- WHEN the answer completes streaming
- THEN the new Q&A pair is visible in the chat
- AND refreshing the page still shows the new pair

## Out of Scope

- Conversation search or full-text search within conversations
- Conversation sharing or export
- Conversation-level access control or multi-tenancy
- Conversation archival or soft-delete
- Real-time collaboration on conversations
- Conversation title generation via LLM (simple truncation only)
