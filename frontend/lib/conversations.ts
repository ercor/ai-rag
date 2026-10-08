/**
 * API client for conversation endpoints.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationAnswer {
  id: string;
  question: string;
  answer: string | null;
  status: string;
  citations: Array<{
    index: number;
    document_id: string;
    document_title: string;
    section_path: string;
    source_path: string;
    chunk_index: number;
    score: number;
  }>;
  created_at: string;
}

export interface ConversationWithAnswers extends Conversation {
  answers: ConversationAnswer[];
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
}

/**
 * List conversations ordered by most recently updated.
 */
export async function listConversations(
  limit: number = 20,
  offset: number = 0
): Promise<ConversationListResponse> {
  const res = await fetch(
    `${API_BASE}/v1/conversations?limit=${limit}&offset=${offset}`
  );

  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * Get a conversation with all its answers.
 */
export async function getConversation(
  id: string
): Promise<ConversationWithAnswers> {
  const res = await fetch(`${API_BASE}/v1/conversations/${id}`);

  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * Create a new conversation.
 */
export async function createConversation(
  title?: string
): Promise<Conversation> {
  const res = await fetch(`${API_BASE}/v1/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title || null }),
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * Delete a conversation and all its answers.
 */
export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/v1/conversations/${id}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `HTTP ${res.status}`);
  }
}
