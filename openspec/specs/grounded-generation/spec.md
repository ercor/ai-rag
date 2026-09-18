# Grounded Generation Specification

## Purpose

Define the LLM generation pipeline that produces answers grounded in retrieved chunks, validates citations, and streams responses via SSE.

## Requirements

### Requirement: Grounded Answer Prompt

The system SHALL construct a prompt that includes retrieved chunks as numbered context passages and instructs the LLM to cite sources using `[N]` notation.

The prompt MUST instruct the model to respond with `insufficient_evidence` if the context does not contain enough information.

#### Scenario: Context provided

- GIVEN 3 retrieved chunks labeled [1], [2], [3]
- WHEN the prompt is constructed
- THEN the system prompt includes all 3 chunks with their IDs and citation instructions

#### Scenario: Empty context

- GIVEN zero chunks retrieved (should not reach generation due to abstention)
- WHEN generation is somehow triggered
- THEN the system returns `insufficient_evidence` without calling the LLM

### Requirement: LLM Generation via Port

The system SHALL call the `Generator` port to produce the answer text.

The generator MUST use Ollama with the configured model (default: qwen2.5). Generation MUST support streaming token-by-token.

#### Scenario: Successful generation

- GIVEN a valid prompt with context
- WHEN the Generator port is called
- THEN the LLM returns an answer containing `[N]` citation markers referencing context IDs

#### Scenario: LLM unavailable

- GIVEN Ollama is not running
- WHEN generation is requested
- THEN the system returns a `503` error with message indicating the generator is unavailable

### Requirement: Citation Validation

The system SHALL validate that every `[N]` citation in the generated answer references a valid context chunk ID.

Invalid citations MUST be stripped or the answer flagged. The validator MUST run as a post-generation step.

#### Scenario: Valid citations

- GIVEN an answer containing `[1]` and `[3]` where chunks 1 and 3 exist in context
- WHEN validation runs
- THEN both citations pass; the answer is returned unchanged

#### Scenario: Invalid citation stripped

- GIVEN an answer containing `[5]` where chunk 5 does NOT exist in context
- WHEN validation runs
- THEN `[5]` is stripped from the answer; valid citations remain

#### Scenario: All citations invalid

- GIVEN an answer where every citation is invalid
- WHEN validation runs
- THEN the answer is returned with all citations removed; a warning is logged

### Requirement: SSE Streaming

The system SHALL stream the generated answer token-by-token via Server-Sent Events at `GET /v1/answers/{id}/stream`.

The stream MUST include citation metadata after the answer completes.

#### Scenario: Streaming response

- GIVEN a generated answer
- WHEN the client connects to the SSE endpoint
- THEN tokens arrive incrementally as `data: {"token": "..."}\n\n` events

#### Scenario: Stream completion

- GIVEN all tokens have been streamed
- WHEN the stream ends
- THEN a final event is sent: `data: {"done": true, "citations": [...]}\n\n`

#### Scenario: Client disconnect

- GIVEN a streaming response in progress
- WHEN the client disconnects mid-stream
- THEN the server stops generation and cleans up resources without error

### Requirement: Answer Persistence

The system SHALL persist each answer (question, answer text, citations, chunk IDs) via the `AnswerRepository` port.

#### Scenario: Answer stored

- GIVEN a completed generation with validated citations
- WHEN the answer is finalized
- THEN it is stored with a unique ID, query text, answer text, and citation list
