"use client";

import { useState } from "react";
import { submitFeedback } from "@/lib/sse";

interface FeedbackButtonsProps {
  answerId: string | null;
  disabled: boolean;
}

export default function FeedbackButtons({ answerId, disabled }: FeedbackButtonsProps) {
  const [voted, setVoted] = useState<"up" | "down" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleVote = async (vote: "up" | "down") => {
    if (!answerId || disabled || voted) return;

    try {
      await submitFeedback(answerId, vote);
      setVoted(vote);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit feedback");
    }
  };

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => handleVote("up")}
        disabled={disabled || voted !== null}
        className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
          voted === "up"
            ? "bg-green-100 text-green-700"
            : "bg-slate-100 text-slate-600 hover:bg-green-50 hover:text-green-600"
        } disabled:opacity-40 disabled:cursor-not-allowed`}
        aria-label="Thumbs up"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
        </svg>
        {voted === "up" && "Thanks!"}
      </button>
      <button
        type="button"
        onClick={() => handleVote("down")}
        disabled={disabled || voted !== null}
        className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
          voted === "down"
            ? "bg-red-100 text-red-700"
            : "bg-slate-100 text-slate-600 hover:bg-red-50 hover:text-red-600"
        } disabled:opacity-40 disabled:cursor-not-allowed`}
        aria-label="Thumbs down"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
        </svg>
        {voted === "down" && "Noted"}
      </button>
      {error && (
        <span className="text-xs text-red-500">{error}</span>
      )}
    </div>
  );
}
