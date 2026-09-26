// Category grouping + relation-cluster helpers for the dashboard-style /grammar list.
// See docs/plan.md "Grammar dashboard" task + SPEC.md idea doc §46 ("Progress by grammar
// category"). Deliberately reads the real `tags` field off GET /grammar rather than
// hardcoding a category list: a parallel content-authoring agent is populating
// category/level/lesson tags on N4/N2 items right now (N3 has none yet, ADR-4), and this
// must keep working generically as more categories/levels land.
//
// Observed live shape of `tags` (see backend/app/llms_txt.py + a live GET /grammar check):
// each item's tags mix three unrelated things in one flat array:
//   - a level tag equal to item.level ("N4"/"N2") — redundant with the `level` field
//   - a `lesson:NN` tag (N2 only) — not a semantic category
//   - zero or more semantic category tags ("modality", "aspect", "conditionals", ...)
// Category tags additionally come in inconsistent casing across authoring batches
// ("Modality" vs "modality") — normalize case-insensitively before grouping/labeling.

import type { GrammarWithProgressOut, GrammarRelationEdge, GrammarStatus } from "./types";

const LESSON_TAG_RE = /^lesson:/i;
const LEVEL_TAG_RE = /^N[234]$/i;

const OTHER_CATEGORY = "__other__";

/** Extract the normalized (lowercased) semantic category tags for one item, filtering out
 * the level/lesson tags. Empty array (no category tags yet, e.g. all of N3 today) maps the
 * item into the catch-all "Другое" bucket by the caller. */
export function categoryTagsOf(item: GrammarWithProgressOut): string[] {
  const seen = new Set<string>();
  for (const raw of item.tags) {
    if (LESSON_TAG_RE.test(raw) || LEVEL_TAG_RE.test(raw)) continue;
    seen.add(raw.toLowerCase());
  }
  return [...seen];
}

// Russian labels for the categories currently in use across N4/N2 authoring (per the
// content agent's brief). Anything not in this map falls back to a capitalized version of
// the raw tag, so a newly-added category still renders sensibly instead of disappearing.
const CATEGORY_LABELS: Record<string, string> = {
  modality: "Модальность",
  aspect: "Вид действия",
  "giving-receiving": "Давать и получать",
  causative: "Каузатив",
  passive: "Пассив",
  honorifics: "Вежливая речь",
  conditionals: "Условные конструкции",
  comparison: "Сравнение",
  hearsay: "Пересказ, слухи",
  time: "Время",
  causality: "Причина и следствие",
  contrast: "Противопоставление",
  connective: "Связки",
  emphasis: "Усиление",
  quantity: "Количество",
  degree: "Степень",
  manner: "Образ действия",
  nominalizer: "Номинализация",
  obligation: "Долженствование",
  request: "Просьба",
  purpose: "Цель",
  [OTHER_CATEGORY]: "Другое",
};

export function categoryLabel(category: string): string {
  return (
    CATEGORY_LABELS[category] ??
    category.charAt(0).toUpperCase() + category.slice(1).replace(/-/g, " ")
  );
}

export interface CategorySection {
  key: string;
  label: string;
  items: GrammarWithProgressOut[];
}

/** Group items into category sections. An item with 2+ category tags appears in each of
 * its sections (faceted, not partitioned) — more useful for browsing than an arbitrary
 * "primary category" pick. Items with zero category tags (all N3 today) land in "Другое". */
export function groupByCategory(items: GrammarWithProgressOut[]): CategorySection[] {
  const buckets = new Map<string, GrammarWithProgressOut[]>();
  for (const item of items) {
    const cats = categoryTagsOf(item);
    const keys = cats.length > 0 ? cats : [OTHER_CATEGORY];
    for (const key of keys) {
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key)!.push(item);
    }
  }
  const sections = [...buckets.entries()].map(([key, sectionItems]) => ({
    key,
    label: categoryLabel(key),
    items: sectionItems,
  }));
  // "Другое" always last; the rest alphabetical by Russian label so the list reads cleanly.
  sections.sort((a, b) => {
    if (a.key === OTHER_CATEGORY) return 1;
    if (b.key === OTHER_CATEGORY) return -1;
    return a.label.localeCompare(b.label, "ru");
  });
  return sections;
}

/** % of items in `items` that are "mastered" — used for the per-section and per-cluster
 * mastery indicator. Returns null when there's nothing to measure. */
export function masteryPct(items: { status: GrammarStatus }[]): number | null {
  if (items.length === 0) return null;
  const mastered = items.filter((i) => i.status === "mastered").length;
  return Math.round((mastered / items.length) * 100);
}

export interface RelationCluster {
  id: string;
  label: string;
  summary: string;
  members: GrammarWithProgressOut[];
}

// `meaning_ru` is the example sentence's translation, not the grammar point's own gloss — the
// actual "what does this construction mean" text lives inside `pattern_text` after "Значение:"
// (both N3's Anki-derived and N4/N2's authored content follow this "Паттерн: ... \nЗначение:
// ..." convention). Pull just that part for a short Russian summary of what a cluster is about.
function meaningGloss(patternText: string): string {
  const match = /Значение:\s*(.+)/s.exec(patternText);
  const text = (match?.[1] ?? patternText).split("\n")[0]?.trim() ?? "";
  return text.length > 60 ? `${text.slice(0, 57)}…` : text;
}

/** Connected components over the relation edge graph (undirected — direction only matters
 * for display elsewhere, not for clustering). Returns clusters of 2+ members, largest first.
 * Pure client-side graph traversal per docs/plan.md — no new backend endpoint. */
export function computeRelationClusters(
  items: GrammarWithProgressOut[],
  edges: GrammarRelationEdge[],
): RelationCluster[] {
  const byId = new Map(items.map((item) => [item.id, item]));
  const adjacency = new Map<string, Set<string>>();
  const degree = new Map<string, number>();

  const link = (a: string, b: string) => {
    if (!byId.has(a) || !byId.has(b)) return;
    if (!adjacency.has(a)) adjacency.set(a, new Set());
    if (!adjacency.has(b)) adjacency.set(b, new Set());
    adjacency.get(a)!.add(b);
    adjacency.get(b)!.add(a);
    degree.set(a, (degree.get(a) ?? 0) + 1);
    degree.set(b, (degree.get(b) ?? 0) + 1);
  };
  for (const edge of edges) {
    link(edge.grammar_id, edge.related_grammar_id);
  }

  const visited = new Set<string>();
  const clusters: RelationCluster[] = [];
  for (const nodeId of adjacency.keys()) {
    if (visited.has(nodeId)) continue;
    const componentIds: string[] = [];
    const stack = [nodeId];
    visited.add(nodeId);
    while (stack.length > 0) {
      const current = stack.pop()!;
      componentIds.push(current);
      for (const neighbor of adjacency.get(current) ?? []) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          stack.push(neighbor);
        }
      }
    }
    if (componentIds.length < 2) continue;
    const members = componentIds
      .map((id) => byId.get(id))
      .filter((item): item is GrammarWithProgressOut => item !== undefined)
      // Highest-degree (most interconnected) member first — becomes the cluster's
      // representative label and reads as "the thing everything else is confused with".
      .sort((a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0));
    if (members.length < 2) continue;
    // The bare grammar form (target_construction, e.g. "ようだ"), not expression_clean (the
    // full example sentence) — a cluster of 10+ members reads as a wall of unrelated
    // sentences if the "name" is two random full sentences stitched together.
    const headline = members
      .slice(0, 2)
      .map((m) => m.target_construction)
      .join(" / ");
    // Short Russian summary of what the cluster is actually about, not just its Japanese
    // forms — dedup identical glosses (small clusters often share near-identical meanings).
    const glosses = Array.from(
      new Set(members.slice(0, 3).map((m) => meaningGloss(m.pattern_text)).filter(Boolean)),
    );
    clusters.push({
      id: componentIds.slice().sort().join("-"),
      label: headline,
      summary: glosses.join(" · "),
      members,
    });
  }
  clusters.sort((a, b) => b.members.length - a.members.length);
  return clusters;
}
