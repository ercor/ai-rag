"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation } from "@/lib/sse";
import CitationBadge from "./CitationBadge";

interface AnswerDisplayProps {
  answerText: string;
  citations: Citation[];
  status: "idle" | "loading" | "streaming" | "answered" | "insufficient_evidence" | "conflicting_evidence" | "policy_blocked" | "failed";
  error: string | null;
}

/**
 * Parse answer text and interleave citation badges at [N] markers.
 */
function renderWithCitations(text: string, citations: Citation[]): React.ReactNode {
  // Split text on citation markers like [1], [2], [1,2], [3]
  const parts = text.split(/(\[\d+(?:,\s*\d+)*\])/g);

  return parts.map((part, i) => {
    const citationMatch = part.match(/^\[(\d+(?:,\s*\d+)*)\]$/);
    if (citationMatch) {
      const indices = citationMatch[1].split(/,\s*/).map(Number);
      return (
        <span key={i}>
          {indices.map((idx) => {
            const citation = citations.find((c) => c.index === idx);
            if (!citation) return null;
            return <CitationBadge key={idx} index={idx} citation={citation} />;
          })}
        </span>
      );
    }
    // Render markdown for text segments
    return (
      <ReactMarkdown key={i} remarkPlugins={[remarkGfm]}>
        {part}
      </ReactMarkdown>
    );
  });
}

export default function AnswerDisplay({ answerText, citations, status, error }: AnswerDisplayProps) {
  // Loading state
  if (status === "loading") {
    return (
      <div className="flex items-center gap-3 text-slate-500">
        <div className="flex gap-1">
          <span className="h-2 w-2 rounded-full bg-blue-400 animate-bounce [animation-delay:0ms]" />
          <span className="h-2 w-2 rounded-full bg-blue-400 animate-bounce [animation-delay:150ms]" />
          <span className="h-2 w-2 rounded-full bg-blue-400 animate-bounce [animation-delay:300ms]" />
        </div>
        <span className="text-sm">Searching documents...</span>
      </div>
    );
  }

  // Insufficient evidence
  if (status === "insufficient_evidence") {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
        <div className="flex items-start gap-3">
          <svg className="h-5 w-5 text-amber-500 mt-0.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <div>
            <p className="font-medium text-amber-800">Insufficient evidence</p>
            <p className="text-sm text-amber-700 mt-1">
              I couldn&apos;t find enough information in the available documents to answer this question. Try rephrasing or asking about a different topic.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Conflicting evidence
  if (status === "conflicting_evidence") {
    return (
      <div className="rounded-xl border border-orange-200 bg-orange-50 p-4">
        <div className="flex items-start gap-3">
          <svg className="h-5 w-5 text-orange-500 mt-0.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <div>
            <p className="font-medium text-orange-800">Conflicting evidence</p>
            <p className="text-sm text-orange-700 mt-1">
              The documents contain conflicting information about this topic. Please verify with the original sources.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Policy blocked
  if (status === "policy_blocked") {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4">
        <div className="flex items-start gap-3">
          <svg className="h-5 w-5 text-red-500 mt-0.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
          </svg>
          <div>
            <p className="font-medium text-red-800">Blocked by policy</p>
            <p className="text-sm text-red-700 mt-1">
              This question cannot be answered due to content policy restrictions.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (status === "failed" || error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4">
        <div className="flex items-start gap-3">
          <svg className="h-5 w-5 text-red-500 mt-0.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
          <div>
            <p className="font-medium text-red-800">Something went wrong</p>
            <p className="text-sm text-red-700 mt-1">
              {error || "An unexpected error occurred while generating the answer. Please try again."}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Streaming or answered — render the answer
  if (!answerText && status === "streaming") {
    return (
      <div className="flex items-center gap-2 text-slate-500">
        <div className="flex gap-1">
          <span className="h-2 w-2 rounded-full bg-blue-400 animate-bounce [animation-delay:0ms]" />
          <span className="h-2 w-2 rounded-full bg-blue-400 animate-bounce [animation-delay:150ms]" />
          <span className="h-2 w-2 rounded-full bg-blue-400 animate-bounce [animation-delay:300ms]" />
        </div>
        <span className="text-sm">Generating answer...</span>
      </div>
    );
  }

  if (!answerText) return null;

  return (
    <div className={`prose prose-slate max-w-none ${status === "streaming" ? "typing-cursor" : ""}`}>
      {renderWithCitations(answerText, citations)}
    </div>
  );
}
