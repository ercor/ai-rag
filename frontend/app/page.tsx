"use client";

import { useState, useRef, useCallback } from "react";
import ChatInput from "@/components/ChatInput";
import AnswerDisplay from "@/components/AnswerDisplay";
import SourcePanel from "@/components/SourcePanel";
import FeedbackButtons from "@/components/FeedbackButtons";
import ConversationSidebar from "@/components/ConversationSidebar";
import { createAnswer, streamAnswer, type Citation } from "@/lib/sse";
import type { ConversationWithAnswers } from "@/lib/conversations";

type AnswerStatus =
  | "idle"
  | "loading"
  | "streaming"
  | "answered"
  | "insufficient_evidence"
  | "conflicting_evidence"
  | "policy_blocked"
  | "failed";

interface Message {
  id: string;
  question: string;
  answerText: string;
  citations: Citation[];
  status: AnswerStatus;
  answerId: string | null;
  error: string | null;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const handleSubmit = useCallback(
    async (question: string) => {
      // Cancel any active stream
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }

      const msgId = crypto.randomUUID();
      const newMessage: Message = {
        id: msgId,
        question,
        answerText: "",
        citations: [],
        status: "loading",
        answerId: null,
        error: null,
      };

      setMessages((prev) => [...prev, newMessage]);
      setIsStreaming(true);
      scrollToBottom();

      try {
        // Phase 1: Create answer (sync retrieval)
        const response = await createAnswer(question, currentConversationId || undefined);

        if (response.status === "insufficient_evidence") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === msgId
                ? { ...m, status: "insufficient_evidence" as AnswerStatus }
                : m
            )
          );
          setIsStreaming(false);
          scrollToBottom();
          return;
        }

        if (!response.answer_id) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === msgId
                ? { ...m, status: "failed" as AnswerStatus, error: "No answer ID returned" }
                : m
            )
          );
          setIsStreaming(false);
          scrollToBottom();
          return;
        }

        const answerId = response.answer_id;

        // Update message with answer_id and streaming status
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? { ...m, status: "streaming" as AnswerStatus, answerId }
              : m
          )
        );

        // Phase 2: Stream tokens via SSE
        const controller = streamAnswer(answerId, {
          onToken: (token) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === msgId
                  ? { ...m, answerText: m.answerText + token }
                  : m
              )
            );
            scrollToBottom();
          },
          onDone: (data) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === msgId
                  ? {
                      ...m,
                      answerText: data.answer,
                      citations: data.citations,
                      status: "answered" as AnswerStatus,
                    }
                  : m
              )
            );
            setIsStreaming(false);
            abortRef.current = null;
            scrollToBottom();
          },
          onError: (reason) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === msgId
                  ? { ...m, status: "failed" as AnswerStatus, error: reason }
                  : m
              )
            );
            setIsStreaming(false);
            abortRef.current = null;
            scrollToBottom();
          },
        });

        abortRef.current = controller;
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  status: "failed" as AnswerStatus,
                  error: err instanceof Error ? err.message : "Failed to create answer",
                }
              : m
          )
        );
        setIsStreaming(false);
        scrollToBottom();
      }
    },
    [scrollToBottom]
  );

  // Get the last message for the source panel
  const lastMessage = messages.length > 0 ? messages[messages.length - 1] : null;

  const handleConversationSelect = useCallback((conversation: ConversationWithAnswers) => {
    // Load messages from conversation
    const loadedMessages: Message[] = conversation.answers
      .filter((a) => a.status === "answered")
      .map((a) => ({
        id: a.id,
        question: a.question,
        answerText: a.answer || "",
        citations: a.citations as Citation[],
        status: "answered" as AnswerStatus,
        answerId: a.id,
        error: null,
      }));
    
    setMessages(loadedMessages);
    setCurrentConversationId(conversation.id);
    scrollToBottom();
  }, [scrollToBottom]);

  const handleNewConversation = useCallback(() => {
    setMessages([]);
    setCurrentConversationId(null);
  }, []);

  return (
    <div className="flex h-full">
      {/* Conversation Sidebar */}
      <div className="hidden lg:block w-64 flex-shrink-0">
        <ConversationSidebar
          activeConversationId={currentConversationId}
          onConversationSelect={handleConversationSelect}
          onNewConversation={handleNewConversation}
        />
      </div>

      {/* Main content area */}
      <main className="flex-1 mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 overflow-y-auto">
      {/* Header */}
      <header className="mb-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">AI RAG</h1>
            <p className="text-sm text-slate-500">Ask questions about your documents</p>
          </div>
        </div>
      </header>

      {/* Main layout: responsive side-by-side or stacked */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Chat area */}
        <div className="flex-1 min-w-0">
          {/* Messages */}
          <div className="space-y-6 mb-6">
            {messages.length === 0 && (
              <div className="rounded-xl border border-dashed border-slate-300 bg-white/50 p-8 text-center">
                <svg className="mx-auto h-12 w-12 text-slate-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                <h2 className="mt-4 text-lg font-medium text-slate-600">
                  Ask a question
                </h2>
                <p className="mt-2 text-sm text-slate-400">
                  Type a question below to search your documents and get a grounded answer with citations.
                </p>
              </div>
            )}

            {messages.map((msg) => (
              <div key={msg.id} className="space-y-3">
                {/* Question bubble */}
                <div className="flex justify-end">
                  <div className="max-w-[80%] rounded-2xl bg-blue-600 px-4 py-3 text-white shadow-sm">
                    <p className="text-sm">{msg.question}</p>
                  </div>
                </div>

                {/* Answer bubble */}
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <AnswerDisplay
                    answerText={msg.answerText}
                    citations={msg.citations}
                    status={msg.status}
                    error={msg.error}
                  />
                  {/* Feedback buttons — only show for completed answers */}
                  {(msg.status === "answered") && (
                    <div className="mt-4 pt-3 border-t border-slate-100">
                      <FeedbackButtons
                        answerId={msg.answerId}
                        disabled={msg.status !== "answered"}
                      />
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <div className="sticky bottom-0 bg-gradient-to-t from-slate-50 via-slate-50 to-transparent pt-4 pb-2">
            <ChatInput onSubmit={handleSubmit} disabled={isStreaming} />
          </div>
        </div>

        {/* Source panel — side-by-side on large screens */}
        <aside className="w-full lg:w-80 shrink-0">
          <div className="sticky top-6">
            <SourcePanel
              citations={lastMessage?.citations || []}
              answerId={lastMessage?.answerId || null}
              status={lastMessage?.status || "idle"}
            />
          </div>
        </aside>
      </div>
    </main>
    </div>
  );
}
