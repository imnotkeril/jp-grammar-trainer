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
// The seed/AI sentence markup wraps the tested target as <ruby><b>目</b><rt>め</rt></ruby> —
// the <rt> is a SIBLING of <b>, not nested inside it. `stripFuriganaInsideBold` below must
// also catch this sibling form or it silently never strips anything on real data (the <b>
// span alone never contains an <rt>).
const BOLD_THEN_SIBLING_RT_RE = /(<b>[\s\S]*?<\/b>)<rt>[\s\S]*?<\/rt>/g;

// A handful of rows in the Anki-sourced seed data have a malformed <rt> span whose payload
// is the rest of the sentence (or another bled-in fragment) instead of a short kana reading
// for the immediately preceding base text — see ARCHITECTURE.md ADR-6/ADR-6b; the seed
// import intentionally leaves these un-hand-fixed in the source JSON. Rendered as-is this
// produces a giant, sentence-length furigana annotation over one or two kanji, which reads
// as broken UI. A real reading is never more than a few kana per base character, so any
// <rt> payload far longer than that — relative to the base text it annotates — is dropped
// here rather than rendered, regardless of furigana mode.
const RUBY_PAIR_RE = /<ruby>((?:(?!<\/ruby>)[\s\S])*?)<rt>([\s\S]*?)<\/rt><\/ruby>/g;
const MAX_RT_RATIO = 4;
const MAX_RT_SLACK = 2;

function stripMalformedFurigana(html: string): string {
  return html.replace(RUBY_PAIR_RE, (match, base: string, rt: string) => {
    const baseLength = base.replace(/<[^>]+>/g, "").length || 1;
    const threshold = baseLength * MAX_RT_RATIO + MAX_RT_SLACK;
    if (rt.length > threshold) {
      // Drop the bogus reading but keep the base text visible.
      return base;
    }
    return match;
  });
}

function stripAllFurigana(html: string): string {
  return html.replace(RT_SPAN_RE, "");
}

function stripFuriganaInsideBold(html: string): string {
  const withoutNested = html.replace(BOLD_BLOCK_RE, (match) => match.replace(RT_SPAN_RE, ""));
  return withoutNested.replace(BOLD_THEN_SIBLING_RT_RE, "$1");
}

// ARCHITECTURE.md V3 §V3.4 (ADR-15) — mirrors backend/app/services/furigana.py's
// strip_known_words. Additionally strips <rt> for any <ruby> span whose base text (inner
// tags stripped) exact-matches a currently-known vocabulary surface form. Exact-match only,
// same RUBY_PAIR_RE used by stripMalformedFurigana above so both passes agree on what counts
// as a ruby pair.
const INNER_TAG_RE = /<[^>]+>/g;

function stripKnownWords(html: string, knownSurfaceForms: ReadonlySet<string>): string {
  if (knownSurfaceForms.size === 0) return html;
  return html.replace(RUBY_PAIR_RE, (match, base: string) => {
    const cleanBase = base.replace(INNER_TAG_RE, "");
    return knownSurfaceForms.has(cleanBase) ? base : match;
  });
}

/**
 * Pure function: apply a furigana display mode to ruby-marked-up HTML.
 *
 * - "always": returned as-is — browsers render <ruby><rt> natively.
 * - "never": every <rt> payload stripped.
 * - "by_level": <rt> stripped only inside the <b> (tested target) span — MVP heuristic,
 *   ARCHITECTURE.md ADR-7.
 * - "adaptive": by_level baseline, plus <rt> additionally stripped for any <ruby> span whose
 *   base is a currently-known vocabulary word (ARCHITECTURE.md V3 §V3.4, ADR-15/16).
 */
export function renderFuriganaHtml(
  html: string,
  mode: FuriganaMode,
  knownSurfaceForms: ReadonlySet<string> = new Set(),
): string {
  const sanitized = stripMalformedFurigana(html);
  switch (mode) {
    case "always":
      return sanitized;
    case "never":
      return stripAllFurigana(sanitized);
    case "by_level":
      return stripFuriganaInsideBold(sanitized);
    case "adaptive":
      return stripKnownWords(stripFuriganaInsideBold(sanitized), knownSurfaceForms);
  }
}

interface FuriganaTextProps {
  html: string;
  mode: FuriganaMode;
  className?: string;
  /** Surface forms currently "known" for this session (V3 §V3.4) — only consulted in "adaptive" mode. */
  knownSurfaceForms?: ReadonlySet<string>;
}

export default function FuriganaText({ html, mode, className, knownSurfaceForms }: FuriganaTextProps) {
  const rendered = renderFuriganaHtml(html, mode, knownSurfaceForms);
  // eslint-disable-next-line react/no-danger -- source HTML is our own seed/AI content, not user input
  return <span className={className} dangerouslySetInnerHTML={{ __html: rendered }} />;
}
