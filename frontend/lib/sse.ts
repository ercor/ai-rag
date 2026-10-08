/**
 * SSE client for the ai-rag backend.
 *
 * Uses fetch + ReadableStream (not EventSource) because we need POST
 * to create the answer, then GET the SSE stream.
 */

export interface Citation {
  index: number;
  document_id: string;
  document_title: string;
  section_path: string;
  source_path: string;
  chunk_index: number;
  score: number;
}

export interface CreateAnswerResponse {
  answer_id: string | null;
  status: "streaming" | "insufficient_evidence" | "answered" | "failed";
  answer: string | null;
  citations: Citation[];
}

export interface SSECallbacks {
  onToken: (token: string) => void;
  onDone: (data: { answer: string; citations: Citation[] }) => void;
  onError: (reason: string) => void;
  onAbort?: (reason: string) => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Create an answer by POSTing the question.
 * Returns the response with answer_id and status.
 */
export async function createAnswer(
  question: string,
  conversationId?: string
): Promise<CreateAnswerResponse> {
  const body: { question: string; conversation_id?: string } = { question };
  if (conversationId) {
    body.conversation_id = conversationId;
  }

  const res = await fetch(`${API_BASE}/v1/answers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * Connect to the SSE stream for an answer and invoke callbacks.
 * Returns an AbortController so the caller can cancel the stream.
 */
export function streamAnswer(answerId: string, callbacks: SSECallbacks): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/answers/${answerId}/stream`, {
        method: "GET",
        headers: { Accept: "text/event-stream" },
        signal: controller.signal,
      });

      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: res.statusText }));
        callbacks.onError(detail.detail || `HTTP ${res.status}`);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        callbacks.onError("No response body");
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE events (separated by \n\n)
        const events = buffer.split("\n\n");
        // Keep the last incomplete chunk in the buffer
        buffer = events.pop() || "";

        for (const eventText of events) {
          if (!eventText.trim()) continue;
          // Skip keepalive comments
          if (eventText.trim().startsWith(":")) continue;

          const eventMatch = eventText.match(/^event:\s*(.+)$/m);
          const dataMatch = eventText.match(/^data:\s*(.*)$/m);

          if (!eventMatch || !dataMatch) continue;

          const eventType = eventMatch[1].trim();
          const eventData = dataMatch[1];

          switch (eventType) {
            case "token":
              callbacks.onToken(eventData);
              break;
            case "done":
              try {
                const parsed = JSON.parse(eventData);
                callbacks.onDone(parsed);
              } catch {
                callbacks.onError("Failed to parse done event");
              }
              return;
            case "error":
              try {
                const parsed = JSON.parse(eventData);
                callbacks.onError(parsed.reason || "Unknown error");
              } catch {
                callbacks.onError(eventData);
              }
              return;
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        callbacks.onAbort?.("Stream cancelled");
        return;
      }
      callbacks.onError(err instanceof Error ? err.message : "Stream failed");
    }
  })();

  return controller;
}

/**
 * Submit feedback (thumbs up/down) for an answer.
 */
export async function submitFeedback(
  answerId: string,
  vote: "up" | "down"
): Promise<void> {
  const res = await fetch(`${API_BASE}/v1/answers/${answerId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ vote }),
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `HTTP ${res.status}`);
  }
}
