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
