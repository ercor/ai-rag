# Delta for Chat UI

## MODIFIED Requirements

### Requirement: Responsive Layout

The system SHALL render the chat interface responsively for desktop and tablet viewports.

The layout SHALL include a conversation sidebar on the left side for desktop viewports. The sidebar MAY collapse to a hamburger menu or drawer on tablet/mobile viewports.

(Previously: The layout had only the answer area and source panel with no sidebar.)

#### Scenario: Desktop layout

- GIVEN a viewport width >= 1024px
- WHEN the chat UI renders
- THEN the conversation sidebar, answer area, and source panel are displayed (sidebar | answer | sources)

#### Scenario: Tablet layout

- GIVEN a viewport width < 1024px
- WHEN the chat UI renders
- THEN the source panel is displayed below the answer area
- AND the conversation sidebar is accessible via a hamburger menu or drawer toggle

## ADDED Requirements

### Requirement: Conversation Sidebar

The system SHALL provide a conversation sidebar component that displays the user's conversation list, allows creating new conversations, switching between conversations, and deleting conversations.

The sidebar MUST fetch conversations from `GET /v1/conversations` on mount. The sidebar MUST highlight the currently active conversation. The sidebar MUST provide a "New Conversation" button.

#### Scenario: Sidebar loads conversations

- GIVEN the user opens the application
- WHEN the sidebar mounts
- THEN it calls `GET /v1/conversations` and displays the returned list
- AND each entry shows the conversation title and relative time (e.g., "2 hours ago")

#### Scenario: Active conversation highlighted

- GIVEN the user is viewing conversation "conv-123"
- WHEN the sidebar renders
- THEN the "conv-123" entry is visually highlighted (e.g., background color, border)

#### Scenario: New conversation button

- GIVEN the sidebar is rendered
- WHEN the user clicks "New Conversation"
- THEN `POST /v1/conversations` is called
- AND the new conversation appears at the top of the sidebar
- AND the chat area is cleared for the new conversation

#### Scenario: Switch conversation

- GIVEN the user clicks a different conversation in the sidebar
- WHEN the click is registered
- THEN `GET /v1/conversations/{id}` is called to load the conversation's messages
- AND the chat area displays the loaded message history
- AND the sidebar highlights the newly selected conversation

#### Scenario: Delete conversation from sidebar

- GIVEN the user hovers over or selects a conversation in the sidebar
- WHEN the delete action is triggered
- THEN a confirmation prompt is shown
- AND upon confirmation, `DELETE /v1/conversations/{id}` is called
- AND the conversation is removed from the sidebar list
- AND if the deleted conversation was active, the chat switches to the next most recent conversation or an empty state

### Requirement: Message Persistence via Conversations

The system SHALL load messages from the API when a conversation is selected, replacing the previous in-memory-only message storage.

Messages MUST be fetched from `GET /v1/conversations/{id}` which returns the conversation's answers. Each answer provides the question and answer text. The messages array is rebuilt from the API response.

#### Scenario: Messages loaded from API

- GIVEN the user selects conversation "conv-123"
- WHEN the conversation loads
- THEN `GET /v1/conversations/conv-123` is called
- AND the returned answers are rendered as message pairs (question + answer) in the chat area

#### Scenario: New messages persisted

- GIVEN the user asks a question in an active conversation
- WHEN the answer completes
- THEN the question and answer are sent to `POST /v1/answers` with the `conversation_id`
- AND the message appears in the chat
- AND refreshing the page and re-selecting the conversation shows the same messages

#### Scenario: Empty state for new conversation

- GIVEN the user creates a new conversation with no messages
- WHEN the conversation is selected
- THEN the chat area shows an empty state (e.g., "Ask a question to get started")

### Requirement: Conversation API Client

The system SHALL provide API client functions in the frontend for conversation operations.

Functions: `listConversations()`, `getConversation(id)`, `createConversation(title?)`, `deleteConversation(id)`.

#### Scenario: List conversations

- GIVEN the API client is imported
- WHEN `listConversations()` is called
- THEN it calls `GET /v1/conversations` and returns the parsed response

#### Scenario: Create conversation

- GIVEN the API client is imported
- WHEN `createConversation("My Chat")` is called
- THEN it calls `POST /v1/conversations` with `{"title": "My Chat"}` and returns the new conversation

#### Scenario: Delete conversation

- GIVEN the API client is imported
- WHEN `deleteConversation("conv-123")` is called
- THEN it calls `DELETE /v1/conversations/conv-123`
