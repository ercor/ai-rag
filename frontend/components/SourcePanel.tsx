"use client";

import type { Citation } from "@/lib/sse";

interface SourcePanelProps {
  citations: Citation[];
  answerId: string | null;
  status: string;
}

export default function SourcePanel({ citations, answerId, status }: SourcePanelProps) {
  if (!answerId || citations.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-slate-400">
        {status === "insufficient_evidence"
          ? "No sources found — the question could not be answered from the available documents."
          : status === "failed"
          ? "An error occurred while generating the answer."
          : "Cited sources will appear here."}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">
        Sources ({citations.length})
      </h3>
      <div className="space-y-2">
        {citations.map((c) => (
          <div
            key={`${c.document_id}-${c.chunk_index}`}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300 hover:shadow"
          >
            <div className="flex items-start gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-100 text-blue-700 text-xs font-bold">
                {c.index}
              </span>
              <div className="min-w-0 flex-1">
                <h4 className="font-medium text-slate-900 truncate">
                  {c.document_title}
                </h4>
                {c.section_path && (
                  <p className="text-xs text-slate-500 mt-0.5 truncate">
                    {c.section_path}
                  </p>
                )}
                <p className="text-xs text-slate-400 mt-1 truncate">
                  {c.source_path}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
