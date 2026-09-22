"use client";

// Dashboard — ARCHITECTURE.md §8 / Phase 4 task 4.2.
// Layout follows SPEC's intended shape: due count + Start Review CTA, mastery breakdown,
// recent recall performance. `GET /stats` (ARCHITECTURE.md §8) returns
// {due_count, new_count, learning_count, review_count, mastered_count, recall_pct} — no
// application/discrimination percentages or a weak-areas list exist on that contract (those
// scores live server-side on grammar_progress but aren't exposed via any MVP endpoint), so
// this page shows exactly what lib/api.ts's Stats type provides rather than inventing fields.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Stats } from "@/lib/types";
import { formatPercent } from "@/lib/format";
import DueCounter from "@/components/DueCounter";
import MasteryBar from "@/components/MasteryBar";
import { ErrorBlock, LoadingBlock } from "@/components/StatusBlocks";

type LoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; stats: Stats };

export default function DashboardPage() {
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
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-8 px-4 py-10">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[var(--ink)]">
          Тренажёр грамматики N3
        </h1>
        <p className="mt-1 text-sm text-[var(--ink-muted)]">
          205 конструкций · интервальное повторение
        </p>
      </div>

      {state.status === "loading" && <LoadingBlock label="Загружаю статистику…" />}
      {state.status === "error" && <ErrorBlock onRetry={load} />}

      {state.status === "ready" && (
        <>
          <DueCounter dueCount={state.stats.due_count} />

          <Link
            href="/review"
            className="transition-standard rounded-lg bg-[var(--accent)] px-6 py-4 text-center text-lg font-medium text-[var(--accent-ink)] hover:bg-[var(--accent-hover)]"
          >
            Начать повторение
          </Link>

          <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
            <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-[var(--ink-muted)]">
              Прогресс по конструкциям
            </h2>
            <MasteryBar stats={state.stats} />
          </section>

          <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
            <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-[var(--ink-muted)]">
              Точность (recall)
            </h2>
            <div className="flex items-baseline gap-2">
              <span className="font-display text-4xl font-semibold text-[var(--ink)]">
                {formatPercent(state.stats.recall_pct)}
              </span>
              <span className="text-sm text-[var(--ink-muted)]">
                скользящее среднее по последним ответам
              </span>
            </div>
          </section>
        </>
      )}

      <Link href="/stats" className="text-center text-sm text-[var(--ink-muted)] underline">
        Подробная статистика
      </Link>
    </main>
  );
}
