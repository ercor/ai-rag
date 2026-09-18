"use client";

import { useState } from "react";
import type { Citation } from "@/lib/sse";

interface CitationBadgeProps {
  index: number;
  citation: Citation;
}

export default function CitationBadge({ index, citation }: CitationBadgeProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        onClick={() => setShowTooltip((v) => !v)}
        className="inline-flex items-center justify-center mx-0.5 rounded-full bg-blue-100 text-blue-700 text-xs font-semibold w-5 h-5 hover:bg-blue-200 transition cursor-pointer align-super"
        aria-label={`Source ${index}: ${citation.document_title}`}
      >
        {index}
      </button>
      {showTooltip && (
        <span className="absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-slate-800 px-3 py-2 text-xs text-white shadow-lg">
          <span className="block font-medium">{citation.document_title}</span>
          {citation.section_path && (
            <span className="block text-slate-300 mt-0.5">{citation.section_path}</span>
          )}
          <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-800" />
        </span>
      )}
    </span>
  );
}
