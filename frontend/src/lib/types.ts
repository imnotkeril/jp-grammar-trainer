// Mirrors backend/app/schemas/*.py — see ARCHITECTURE.md §8 for the API surface.

export interface FormationRule {
  pos: string;
  form_label: string;
  example_html: string;
}

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

export interface SessionResponse {
  questions: Question[];
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
}

// Furigana display mode toggle — ARCHITECTURE.md §5. Persisted client-side only (MVP).
export type FuriganaMode = "always" | "never" | "by_level";

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
  limit?: number;
  offset?: number;
}
