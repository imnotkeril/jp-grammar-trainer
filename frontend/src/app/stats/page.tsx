"use client";

// Stats page — ARCHITECTURE.md §8 / Phase 4 task 4.4.
// Fuller detail than the Dashboard summary, but built only from what `GET /stats` actually
// returns (lib/api.ts's Stats type: due_count, new_count, learning_count, review_count,
// mastered_count, recall_pct). No performance-history/trend chart, weak-areas list, or
// application/discrimination scores — those aren't in the API contract (they'd need a
// history endpoint or per-item progress the backend doesn't expose on MVP), so this page
// doesn't fabricate them. SPEC §71/ARCHITECTURE §11 flag richer stats as V2 scope.

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Stats } from "@/lib/types";
import { formatPercent } from "@/lib/format";
import MasteryBar from "@/components/MasteryBar";
import { ErrorBlock, LoadingBlock } from "@/components/StatusBlocks";

const TOTAL_GRAMMAR_ITEMS = 205; // fixed N3 deck size — ARCHITECTURE.md §4/§3, not user-editable

type LoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; stats: Stats };

export default function StatsPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    api
      .getStats()
      .then((stats) => setState({ status: "ready", stats }))
      .catch(() => setState({ status: "error" }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-10">
      <h1 className="font-display text-2xl font-semibold text-[var(--ink)]">Статистика</h1>

      {state.status === "loading" && <LoadingBlock label="Загружаю статистику…" />}
      {state.status === "error" && <ErrorBlock onRetry={load} />}

      {state.status === "ready" && (
        <>
          <section className="grid grid-cols-2 gap-4">
            <StatTile label="К повторению" value={String(state.stats.due_count)} />
            <StatTile label="Recall" value={formatPercent(state.stats.recall_pct)} />
          </section>

          <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
            <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-[var(--ink-muted)]">
              По уровню освоения
            </h2>
            <MasteryBar stats={state.stats} />
          </section>

          <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
            <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-[var(--ink-muted)]">
              Всего конструкций
            </h2>
            <div className="flex items-baseline gap-2">
              <span className="font-display text-3xl font-semibold text-[var(--ink)]">
                {TOTAL_GRAMMAR_ITEMS}
              </span>
              <span className="text-sm text-[var(--ink-muted)]">N3 grammar (Anki seed)</span>
            </div>
            <div className="mt-3 h-2 w-full overflow-hidden rounded-full border border-[var(--border)] bg-[var(--bg)]">
              <div
                className="h-full bg-[var(--success)]"
                style={{
                  width: `${Math.min(100, (state.stats.mastered_count / TOTAL_GRAMMAR_ITEMS) * 100)}%`,
                }}
              />
            </div>
            <p className="mt-2 text-xs text-[var(--ink-muted)]">
              {state.stats.mastered_count} освоено из {TOTAL_GRAMMAR_ITEMS}
            </p>
          </section>
        </>
      )}
    </main>
  );
}

interface StatTileProps {
  label: string;
  value: string;
}

function StatTile({ label, value }: StatTileProps) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <p className="text-xs uppercase tracking-wide text-[var(--ink-muted)]">{label}</p>
      <p className="font-display mt-1 text-3xl font-semibold text-[var(--ink)]">{value}</p>
    </div>
  );
}
