// Shared display labels/colors for grammar status + relation types — used by the V2
// browse/detail/graph views (ARCHITECTURE.md "V2 Slice" §V2.4) so the three pages agree on
// the same Russian copy and color coding instead of drifting independently.

import type { GrammarRelationType, GrammarStatus } from "./types";

export const STATUS_LABELS: Record<GrammarStatus, string> = {
  new: "Новые",
  learning: "Учатся",
  review: "Повторяются",
  mastered: "Освоены",
};

export const STATUS_COLORS: Record<GrammarStatus, string> = {
  new: "bg-[var(--ink-faint)]",
  learning: "bg-[var(--accent)]",
  review: "bg-[var(--success-border)]",
  mastered: "bg-[var(--success)]",
};

// Section headings for the detail page's "Сравнить с…" block, grouped by relation_type.
export const RELATION_TYPE_LABELS: Record<GrammarRelationType, string> = {
  similar_meaning: "Похожее значение",
  similar_form: "Похожая форма",
  commonly_confused: "Часто путают с",
  opposite: "Противоположное",
  prerequisite: "Требует сначала выучить",
  advanced_version: "Продвинутая версия",
  related: "Связано с",
};

// Direction-aware label override for the two directional types (ADR-11) — takes precedence
// over RELATION_TYPE_LABELS when direction isn't "symmetric".
export function relationLabel(
  relationType: GrammarRelationType,
  direction: "symmetric" | "outgoing" | "incoming",
): string {
  if (relationType === "prerequisite") {
    return direction === "incoming" ? "Требует сначала выучить" : "Предшествует для";
  }
  if (relationType === "advanced_version") {
    // ADR-11: (A, B, advanced_version) = "B is the advanced version of A". Viewed from A
    // ("outgoing", the base/simpler item) the related item B is the advanced one; viewed
    // from B ("incoming", the advanced item) the related item A is the simpler base form.
    return direction === "outgoing" ? "Продвинутая версия" : "Более простая форма";
  }
  return RELATION_TYPE_LABELS[relationType];
}

// Legend / edge colors for the canvas graph view — matches the hanko-red warm palette
// rather than default rainbow chart colors.
export const RELATION_TYPE_COLORS: Record<GrammarRelationType, string> = {
  similar_meaning: "#3d6b3f",
  similar_form: "#3a6ea8",
  commonly_confused: "#a8391c",
  opposite: "#8a5fb0",
  prerequisite: "#b58a2a",
  advanced_version: "#c76b2a",
  related: "#8a7f68",
};

export const RELATION_ORDER: GrammarRelationType[] = [
  "commonly_confused",
  "similar_meaning",
  "similar_form",
  "opposite",
  "prerequisite",
  "advanced_version",
  "related",
];
