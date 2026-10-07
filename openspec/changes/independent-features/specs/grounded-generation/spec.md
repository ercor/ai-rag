# Delta for Grounded Generation

## MODIFIED Requirements

### Requirement: Grounded Answer Prompt

The system SHALL construct a prompt that includes retrieved chunks as numbered context passages and instructs the LLM to cite sources using `[N]` notation.

The prompt MUST instruct the model to respond with `insufficient_evidence` if the context does not contain enough information.

When conversation history is available (a `conversation_id` is provided and prior messages exist), the prompt SHALL include a "Conversation History" section before the "Context" section. The history section contains the last N Q&A pairs (configurable via `max_conversation_history`, default: 5), formatted as alternating "Q:" and "A:" blocks. The history section is omitted when no conversation context is available.

(Previously: The prompt contained only Context, Question, and Answer sections with no conversation history.)

#### Scenario: Context provided without history

- GIVEN 3 retrieved chunks labeled [1], [2], [3] and no conversation history
- WHEN the prompt is constructed
- THEN the prompt includes all 3 chunks with their IDs and citation instructions
- AND no "Conversation History" section is present

#### Scenario: Context provided with history

- GIVEN 3 retrieved chunks and 2 prior Q&A exchanges in the conversation
- WHEN the prompt is constructed
- THEN the prompt includes a "Conversation History" section with the 2 prior exchanges
- AND the "Context" section follows the history
- AND the "Question" section contains the current question

#### Scenario: History truncated to max

- GIVEN 10 prior exchanges and `max_conversation_history=5`
- WHEN the prompt is constructed
- THEN only the last 5 exchanges appear in the "Conversation History" section

#### Scenario: Empty context

- GIVEN zero chunks retrieved (should not reach generation due to abstention)
- WHEN generation is somehow triggered
- THEN the system returns `insufficient_evidence` without calling the LLM

## ADDED Requirements

### Requirement: Conversation History in Prompt

The system SHALL accept an optional list of prior Q&A exchanges and include them in the generation prompt.

The history MUST be formatted as alternating "Q: {question}" and "A: {answer}" blocks, separated by blank lines. The history section header MUST be "## Conversation History". The history MUST appear before the "## Context" section in the prompt.

#### Scenario: History formatted correctly

- GIVEN 2 prior exchanges: Q1="What is PTO?", A1="PTO is..." and Q2="How do I request it?", A2="Submit..."
- WHEN the prompt is built with history
- THEN the prompt contains:
  ```
  ## Conversation History

  Q: What is PTO?
  A: PTO is...

  Q: How do I request it?
  A: Submit...

  ## Context
  ...
  ```

#### Scenario: No history provided

- GIVEN `history=None` or an empty list
- WHEN the prompt is built
- THEN no "Conversation History" section is present in the prompt
- AND the prompt structure is identical to the pre-history prompt
