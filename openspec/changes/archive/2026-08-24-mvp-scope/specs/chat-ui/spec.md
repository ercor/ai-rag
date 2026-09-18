# Chat UI Specification

## Purpose

Define the Next.js chat interface that lets users ask questions, view streaming answers with inline citations, and interact with source documents.

## Requirements

### Requirement: Chat Input and Submission

The system SHALL provide a text input for questions with a submit button.

Submission MUST be disabled while an answer is streaming. The input MUST support Enter-to-submit.

#### Scenario: Normal submission

- GIVEN the user types a question
- WHEN they press Enter or click Submit
- THEN the question is sent to `POST /v1/answers` and the UI enters streaming state

#### Scenario: Empty input blocked

- GIVEN the input is empty
- WHEN the user presses Enter
- THEN no request is sent; the submit action is ignored

### Requirement: Streaming Answer Display

The system SHALL display the answer incrementally as SSE tokens arrive.

The display MUST show a typing indicator while streaming and render the final answer with markdown formatting.

#### Scenario: Token-by-token rendering

- GIVEN the SSE stream is active
- WHEN tokens arrive
- THEN each token is appended to the answer display in real time

#### Scenario: Insufficient evidence display

- GIVEN the backend returns `insufficient_evidence`
- WHEN the response arrives
- THEN the UI displays a clear message: "I couldn't find enough information to answer that."

### Requirement: Inline Citation Display

The system SHALL render `[N]` citation markers in the answer as clickable elements that link to the source chunk.

Each citation MUST show the source document name and section path on hover or click.

#### Scenario: Citations rendered

- GIVEN an answer containing `[1]` and `[2]`
- WHEN the answer is displayed
- THEN `[1]` and `[2]` appear as styled, clickable citation badges

#### Scenario: Citation source display

- GIVEN the user clicks citation `[1]`
- WHEN the citation detail is shown
- THEN the source document name and section path for chunk 1 are displayed

### Requirement: Source List Panel

The system SHALL display a list of all cited source documents below or beside the answer.

Each source entry MUST show the document name, section path, and a snippet of the cited chunk.

#### Scenario: Sources displayed

- GIVEN an answer with 3 citations from 2 different documents
- WHEN the answer is fully rendered
- THEN the source panel shows 2 document entries with their relevant sections

### Requirement: Feedback Buttons

The system SHALL provide thumbs-up and thumbs-down buttons after each answer.

Feedback MUST be sent to the backend. The buttons MUST be disabled until the answer is complete.

#### Scenario: Positive feedback

- GIVEN a completed answer
- WHEN the user clicks thumbs-up
- THEN `POST /v1/answers/{id}/feedback` is called with `{"vote": "up"}`

#### Scenario: Feedback before completion blocked

- GIVEN the answer is still streaming
- WHEN the feedback buttons are visible
- THEN they are disabled (greyed out)

### Requirement: Responsive Layout

The system SHALL render the chat interface responsively for desktop and tablet viewports.

#### Scenario: Desktop layout

- GIVEN a viewport width >= 1024px
- WHEN the chat UI renders
- THEN the answer area and source panel are displayed side by side

#### Scenario: Tablet layout

- GIVEN a viewport width < 1024px
- WHEN the chat UI renders
- THEN the source panel is displayed below the answer area
