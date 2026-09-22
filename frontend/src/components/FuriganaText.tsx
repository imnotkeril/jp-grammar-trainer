// Renders ruby-marked-up HTML (from the Anki-sourced seed data or AI-generated sentences)
// under the three furigana display modes from SPEC §4.6 / ARCHITECTURE.md §5.
//
// Reuses the source's existing <ruby><rt> markup instead of building a furigana engine —
// see ARCHITECTURE.md §5. Mirrors backend/app/services/furigana.py's pure-function logic
// so both layers can independently render the same rules (frontend needs client-side
// re-render on toggle without a round-trip; backend needs it for stored sentence_full_html
// in non-UI contexts, e.g. future export/print).

import type { FuriganaMode } from "@/lib/types";

// [\s\S] instead of the /s (dotAll) flag for broader TS target compatibility.
const RT_SPAN_RE = /<rt>[\s\S]*?<\/rt>/g;
const BOLD_BLOCK_RE = /<b>[\s\S]*?<\/b>/g;

function stripAllFurigana(html: string): string {
  return html.replace(RT_SPAN_RE, "");
}

function stripFuriganaInsideBold(html: string): string {
  return html.replace(BOLD_BLOCK_RE, (match) => match.replace(RT_SPAN_RE, ""));
}

/**
 * Pure function: apply a furigana display mode to ruby-marked-up HTML.
 *
 * - "always": returned as-is — browsers render <ruby><rt> natively.
 * - "never": every <rt> payload stripped.
 * - "by_level": <rt> stripped only inside the <b> (tested target) span — MVP heuristic,
 *   ARCHITECTURE.md ADR-7. True per-word adaptive furigana is V2.
 */
export function renderFuriganaHtml(html: string, mode: FuriganaMode): string {
  switch (mode) {
    case "always":
      return html;
    case "never":
      return stripAllFurigana(html);
    case "by_level":
      return stripFuriganaInsideBold(html);
  }
}

interface FuriganaTextProps {
  html: string;
  mode: FuriganaMode;
  className?: string;
}

export default function FuriganaText({ html, mode, className }: FuriganaTextProps) {
  const rendered = renderFuriganaHtml(html, mode);
  // eslint-disable-next-line react/no-danger -- source HTML is our own seed/AI content, not user input
  return <span className={className} dangerouslySetInnerHTML={{ __html: rendered }} />;
}
