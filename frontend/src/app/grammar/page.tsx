"use client";

// Grammar browse/list — ARCHITECTURE.md "V2 Slice" §V2.4 (task V2.7).
// Fetches GET /grammar once (205 rows is a trivial payload), then does search/status
// filtering client-side — the backend's ?q=/status= params exist for forward-compat
// (§V2.3) but a personal single-user 205-item list doesn't need a round-trip per keystroke.

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { GrammarStatus, GrammarWithProgressOut, LevelFilter } from "@/lib/types";
import { STATUS_COLORS, STATUS_LABELS } from "@/lib/grammar";
import { ErrorBlock, LoadingBlock } from "@/components/StatusBlocks";

type LoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; items: GrammarWithProgressOut[] };

const STATUS_FILTERS: GrammarStatus[] = ["new", "learning", "review", "mastered"];

// ARCHITECTURE.md V4 §V4.5 — the Grammar list page's own level filter chips stay page-local
// (default "all"), independent of the header's global LevelSelector/level-context, same as
// the existing status filter chips already are.
const LEVEL_FILTERS: LevelFilter[] = ["N3", "N4", "N2"];
const LEVEL_LABELS: Record<LevelFilter, string> = { N3: "N3", N4: "N4", N2: "N2", all: "Все" };

export default function GrammarListPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<GrammarStatus | null>(null);
  const [levelFilter, setLevelFilter] = useState<LevelFilter>("all");

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    // V4: the backend's default limit (205) predates N4/N2 — now that there are ~496 items
    // across all three levels, an unbounded call truncates to the first 205 (all N3), silently
    // hiding N4/N2 from this page. Request everything explicitly.
    api
      .listGrammar({ limit: 1000 })
      .then((res) => {
        if (!cancelled) setState({ status: "ready", items: res.items });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    if (state.status !== "ready") return [];
    const q = query.trim().toLowerCase();
    return state.items.filter((item) => {
      if (statusFilter && item.status !== statusFilter) return false;
      if (levelFilter !== "all" && item.level !== levelFilter) return false;
      if (!q) return true;
      return (
        item.expression_clean.toLowerCase().includes(q) ||
        item.reading.toLowerCase().includes(q) ||
        item.meaning_ru.toLowerCase().includes(q)
      );
    });
  }, [state, query, statusFilter, levelFilter]);

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-10">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-semibold text-[var(--ink)]">Грамматика</h1>
          <p className="mt-1 text-sm text-[var(--ink-muted)]">
            Все конструкции · просмотр вне сессий повторения
          </p>
        </div>
        <Link
          href="/grammar/graph"
          className="transition-standard shrink-0 rounded-full border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm font-medium text-[var(--ink-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
        >
          Граф связей
        </Link>
      </div>

      <div className="flex flex-col gap-3">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск по выражению, чтению или значению…"
          className="transition-standard rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--ink)] placeholder:text-[var(--ink-faint)] focus:border-[var(--accent)]"
        />
        <div className="flex flex-wrap gap-2" role="group" aria-label="Фильтр по статусу">
          <FilterChip active={statusFilter === null} onClick={() => setStatusFilter(null)}>
            Все
          </FilterChip>
          {STATUS_FILTERS.map((s) => (
            <FilterChip key={s} active={statusFilter === s} onClick={() => setStatusFilter(s)}>
              <span aria-hidden className={`mr-1.5 inline-block h-2 w-2 rounded-full ${STATUS_COLORS[s]}`} />
              {STATUS_LABELS[s]}
            </FilterChip>
          ))}
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Фильтр по уровню">
          {(["all", ...LEVEL_FILTERS] as LevelFilter[]).map((lvl) => (
            <FilterChip key={lvl} active={levelFilter === lvl} onClick={() => setLevelFilter(lvl)}>
              {LEVEL_LABELS[lvl]}
            </FilterChip>
          ))}
        </div>
      </div>

      {state.status === "loading" && <LoadingBlock label="Загружаю конструкции…" />}
      {state.status === "error" && (
        <ErrorBlock onRetry={() => setState({ status: "loading" })} />
      )}

      {state.status === "ready" && (
        <>
          <p className="text-xs text-[var(--ink-faint)]">
            {filtered.length} из {state.items.length}
          </p>
          <ul className="flex flex-col gap-2">
            {filtered.map((item) => (
              <li key={item.id}>
                <Link
                  href={`/grammar/${item.id}`}
                  className="transition-standard flex items-center justify-between gap-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-4 hover:border-[var(--accent)]"
                >
                  <div className="min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="jp-text text-lg font-semibold text-[var(--ink)]">
                        {item.expression_clean}
                      </span>
                      <span className="jp-text text-sm text-[var(--ink-muted)]">{item.reading}</span>
                    </div>
                    <p className="mt-0.5 truncate text-sm text-[var(--ink-muted)]">{item.meaning_ru}</p>
                  </div>
                  <span
                    aria-hidden
                    className={`h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_COLORS[item.status]}`}
                    title={STATUS_LABELS[item.status]}
                  />
                </Link>
              </li>
            ))}
            {filtered.length === 0 && (
              <li className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-8 text-center text-sm text-[var(--ink-muted)]">
                Ничего не найдено.
              </li>
            )}
          </ul>
        </>
      )}
    </main>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`transition-standard flex items-center rounded-full border px-3 py-1.5 text-xs font-medium ${
        active
          ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-ink)]"
          : "border-[var(--border)] bg-[var(--surface)] text-[var(--ink-muted)] hover:border-[var(--border-strong)]"
      }`}
    >
      {children}
    </button>
  );
}
