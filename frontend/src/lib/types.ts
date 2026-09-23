// Mirrors backend/app/schemas/*.py — see ARCHITECTURE.md §8 for the API surface.

export interface FormationRule {
  pos: string;
  form_label: string;
  example_html: string;
}

// V4 Slice §V4.1/§V4.5 — JLPT level. "all" (used by the level selector / filter UI, never
// sent to the backend as-is) means "no level filter" — omit the `level` param entirely.
export type GrammarLevel = "N3" | "N4" | "N2";
export type LevelFilter = GrammarLevel | "all";

export interface GrammarItem {
  id: string;
  expression_html: string;
  expression_clean: string;
  reading: string;
  meaning_ru: string;
  pattern_text: string;
  formation_rules: FormationRule[];
  level: string;
  tags: string[];
  target_construction: string;
}

export type GrammarStatus = "new" | "learning" | "review" | "mastered";

export interface QuestionOption {
  key: string;
  text: string;
}

export interface Question {
  id: string;
  grammar_id: string;
  sentence_with_blank_html: string;
  options: QuestionOption[];
}

// V3 §V3.3 — session composition mode. "due" (default) mixes in a small weak-point ratio
// server-side; "confusion"/"weak_points" are dedicated practice modes (§15/§28).
export type ReviewMode = "due" | "confusion" | "weak_points";

export interface SessionRequest {
  size: 5 | 10 | 20;
  mode?: ReviewMode;
  // V4 §V4.4 — optional level filter, null/omitted = due/weak/confusion selection spans all
  // levels together (default, unchanged behavior).
  level?: GrammarLevel;
}

export interface SessionResponse {
  questions: Question[];
  // V3 §V3.4 — surface_form of every vocabulary row currently "known" (known_since set).
  // Threaded down to every FuriganaText render for the session to drive "adaptive" mode.
  known_words: string[];
}

export interface AnswerRequest {
  question_id: string;
  selected_option: string;
  response_time_ms?: number;
}

export interface AnswerResponse {
  is_correct: boolean;
  correct_option: string;
  explanation_ru: string | null;
  sentence_full_html: string;
  next_review: string;
}

export interface Stats {
  due_count: number;
  new_count: number;
  learning_count: number;
  review_count: number;
  mastered_count: number;
  recall_pct: number;
  // V4 §V4.4 (ADR-23) — real count for whichever `level` filter (or all 3 levels combined)
  // was requested; replaces the frontend's old hardcoded TOTAL_GRAMMAR_ITEMS constant.
  total_items: number;
}

// Furigana display mode toggle — ARCHITECTURE.md §5 (MVP: always/never/by_level) + V3 §V3.4
// ("adaptive" — by_level baseline plus known-vocabulary spans stripped, ADR-15/16). Persisted
// client-side only.
export type FuriganaMode = "always" | "never" | "by_level" | "adaptive";

// --- V2 Grammar Graph & Browse — ARCHITECTURE.md "V2 Slice" §V2.3 ---------------------

// GrammarWithProgressOut: GrammarItem + the owner's progress status on that item
// (grammar_progress.status). Bare GrammarItem above stays as-is for callers that only
// need the static grammar fields (kept for forward-compat, not currently used).
export interface GrammarWithProgressOut extends GrammarItem {
  status: GrammarStatus;
}

// GET /grammar now returns this wrapper instead of a bare array — breaking change vs MVP.
export interface GrammarListOut {
  items: GrammarWithProgressOut[];
  total: number;
}

export type GrammarRelationType =
  | "similar_meaning"
  | "similar_form"
  | "commonly_confused"
  | "opposite"
  | "prerequisite"
  | "advanced_version"
  | "related";

export type GrammarRelationDirection = "symmetric" | "outgoing" | "incoming";

export interface RelatedGrammarSummary {
  id: string;
  expression_clean: string;
  reading: string;
  meaning_ru: string;
  target_construction: string;
}

export interface GrammarRelationOut {
  relation_type: GrammarRelationType;
  direction: GrammarRelationDirection;
  strength: number;
  note: string | null;
  related_grammar: RelatedGrammarSummary;
}

// GET /grammar/{id} response — GrammarWithProgressOut + embedded relations.
export interface GrammarDetailOut extends GrammarWithProgressOut {
  relations: GrammarRelationOut[];
}

// GET /grammar/relations bulk edge list — for the graph view (no node payload, just edges).
export interface GrammarRelationEdge {
  grammar_id: string;
  related_grammar_id: string;
  relation_type: GrammarRelationType;
  direction: GrammarRelationDirection;
  strength: number;
}

export interface GrammarListParams {
  q?: string;
  status?: GrammarStatus;
  tag?: string;
  level?: GrammarLevel;
  limit?: number;
  offset?: number;
}
