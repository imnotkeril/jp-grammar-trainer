// Small formatting helpers shared by Dashboard/Stats.

/**
 * `recall_pct` from `GET /stats` isn't documented as a 0..1 fraction vs. a 0..100 value in
 * ARCHITECTURE.md §8 (only the DB column `recall_score` is explicitly 0..1). Defensive
 * formatting: treat anything <= 1 as a fraction (matches how `recall_score` is computed
 * server-side per §6's `rolling_accuracy`), anything above as already a percentage.
 */
export function formatPercent(value: number): string {
  const pct = value <= 1 ? value * 100 : value;
  return `${Math.round(pct)}%`;
}
