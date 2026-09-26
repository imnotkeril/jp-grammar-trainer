"use client";

// Grammar browse — dashboard-style, category-grouped view. Was a flat scroll of all 496
// items; per the owner's brief this replaces that with (1) collapsible category sections
// driven by the real `tags` field (see lib/grammar-categories.ts — N3 has no category tags
// yet per ADR-4, everything there lands in "Другое" until the content agent's tagging pass
// reaches it) and (2) a "Группы похожих конструкций" section surfacing tightly-interconnected
// relation clusters (e.g. わけではない/とは限らない/わけがない/ことはない) computed
// client-side from GET /grammar/relations — no new backend endpoint.
//
// ARCHITECTURE.md V2 Slice §V2.4 origin of this page; SPEC.md idea doc §46 "Progress by
// grammar category" is the original design intent this reorganization fulfills.

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { GrammarStatus, GrammarWithProgressOut, LevelFilter, GrammarRelationEdge } from "@/lib/types";
import { STATUS_COLORS, STATUS_LABELS } from "@/lib/grammar";
import {
  computeRelationClusters,
  groupByCategory,
  masteryPct,
  type CategorySection,
  type RelationCluster,
} from "@/lib/grammar-categories";
import { ErrorBlock, LoadingBlock } from "@/components/StatusBlocks";

type LoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; items: GrammarWithProgressOut[]; edges: GrammarRelationEdge[] };

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
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    // V4: the backend's default limit (205) predates N4/N2 — now that there are ~496 items
    // across all three levels, an unbounded call truncates to the first 205 (all N3), silently
    // hiding N4/N2 from this page. Request everything explicitly.
    Promise.all([api.listGrammar({ limit: 1000 }), api.getAllGrammarRelations()])
      .then(([list, edges]) => {
        if (!cancelled) setState({ status: "ready", items: list.items, edges });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const hasActiveFilter = query.trim() !== "" || statusFilter !== null || levelFilter !== "all";

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (item: GrammarWithProgressOut): boolean => {
      if (statusFilter && item.status !== statusFilter) return false;
      if (levelFilter !== "all" && item.level !== levelFilter) return false;
      if (!q) return true;
      return (
        item.expression_clean.toLowerCase().includes(q) ||
        item.reading.toLowerCase().includes(q) ||
        item.meaning_ru.toLowerCase().includes(q)
      );
    };
  }, [query, statusFilter, levelFilter]);

  const categorySections: CategorySection[] = useMemo(() => {
    if (state.status !== "ready") return [];
    return groupByCategory(state.items);
  }, [state]);

  const clusters: RelationCluster[] = useMemo(() => {
    if (state.status !== "ready") return [];
    return computeRelationClusters(state.items, state.edges);
  }, [state]);

  const totalCount = state.status === "ready" ? state.items.length : 0;
  const visibleCount =
    state.status === "ready" ? state.items.filter(matches).length : 0;

  function toggleSection(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-10">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-semibold text-[var(--ink)]">Грамматика</h1>
          <p className="mt-1 text-sm text-[var(--ink-muted)]">
            Все конструкции · по категориям · вне сессий повторения
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
      {state.status === "error" && <ErrorBlock onRetry={() => setState({ status: "loading" })} />}

      {state.status === "ready" && (
        <>
          <p className="text-xs text-[var(--ink-faint)]">
            {visibleCount} из {totalCount}
          </p>

          {clusters.length > 0 && (
            <ClusterSection clusters={clusters} matches={matches} hasActiveFilter={hasActiveFilter} />
          )}

          <div className="flex flex-col gap-2">
            {categorySections.map((section) => {
              const visibleItems = section.items.filter(matches);
              if (visibleItems.length === 0) return null;
              const isOpen = hasActiveFilter || expanded.has(section.key);
              return (
                <CategoryDisclosure
                  key={section.key}
                  section={section}
                  visibleItems={visibleItems}
                  isOpen={isOpen}
                  onToggle={() => toggleSection(section.key)}
                />
              );
            })}
            {categorySections.every((s) => s.items.filter(matches).length === 0) && (
              <p className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-8 text-center text-sm text-[var(--ink-muted)]">
                Ничего не найдено.
              </p>
            )}
          </div>
        </>
      )}
    </main>
  );
}

function CategoryDisclosure({
  section,
  visibleItems,
  isOpen,
  onToggle,
}: {
  section: CategorySection;
  visibleItems: GrammarWithProgressOut[];
  isOpen: boolean;
  onToggle: () => void;
}) {
  const pct = masteryPct(section.items);
  return (
    <section className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isOpen}
        className="transition-standard flex w-full items-center justify-between gap-3 px-5 py-4 text-left hover:bg-[var(--accent-soft)]/30"
      >
        <span className="flex items-center gap-2 min-w-0">
          <ChevronIcon open={isOpen} />
          <span className="truncate font-medium text-[var(--ink)]">
            {section.label}{" "}
            <span className="font-normal text-[var(--ink-faint)]">({section.items.length})</span>
          </span>
        </span>
        {pct !== null && <MasteryBadge pct={pct} />}
      </button>
      {isOpen && (
        <ul className="flex flex-col gap-2 border-t border-[var(--border)] px-3 py-3">
          {visibleItems.map((item) => (
            <GrammarRow key={item.id} item={item} />
          ))}
        </ul>
      )}
    </section>
  );
}

function ClusterSection({
  clusters,
  matches,
  hasActiveFilter,
}: {
  clusters: RelationCluster[];
  matches: (item: GrammarWithProgressOut) => boolean;
  hasActiveFilter: boolean;
}) {
  const visibleClusters = clusters
    .map((cluster) => ({ cluster, visibleMembers: cluster.members.filter(matches) }))
    .filter(({ visibleMembers }) => visibleMembers.length >= 2);

  if (visibleClusters.length === 0) return null;

  return (
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="font-display text-lg font-semibold text-[var(--ink)]">
          Группы похожих конструкций
        </h2>
        <p className="text-xs text-[var(--ink-muted)]">
          Часто путаемые/связанные наборы — из графа связей
        </p>
      </div>
      <div className="flex flex-col gap-3">
        {visibleClusters.map(({ cluster, visibleMembers }) => (
          <ClusterCard
            key={cluster.id}
            cluster={cluster}
            visibleMembers={hasActiveFilter ? visibleMembers : cluster.members}
          />
        ))}
      </div>
    </section>
  );
}

function ClusterCard({
  cluster,
  visibleMembers,
}: {
  cluster: RelationCluster;
  visibleMembers: GrammarWithProgressOut[];
}) {
  const pct = masteryPct(cluster.members);
  return (
    <div className="rounded-xl border border-[var(--accent)]/30 bg-[var(--surface)] px-5 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="jp-text truncate text-base font-semibold text-[var(--ink)]">{cluster.label}</p>
          {cluster.summary && (
            <p className="mt-0.5 text-sm text-[var(--ink-muted)]">{cluster.summary}</p>
          )}
          <p className="mt-0.5 text-xs text-[var(--ink-faint)]">{cluster.members.length} конструкций в группе</p>
        </div>
        {pct !== null && <MasteryBadge pct={pct} />}
      </div>
      <ul className="mt-3 flex flex-wrap gap-2">
        {visibleMembers.map((member) => (
          <li key={member.id}>
            <Link
              href={`/grammar/${member.id}`}
              className="transition-standard jp-text inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--bg)] px-3 py-1.5 text-sm text-[var(--ink)] hover:border-[var(--accent)]"
            >
              {member.target_construction || member.expression_clean}
              <span
                aria-hidden
                className={`h-1.5 w-1.5 rounded-full ${STATUS_COLORS[member.status]}`}
                title={STATUS_LABELS[member.status]}
              />
            </Link>
          </li>
        ))}
      </ul>
      {/* NOTE(frontend-dev): true per-cluster practice sessions need POST /review/session's
          "confusion" mode to accept a scoped set of grammar ids — today it pools ALL
          commonly_confused-connected items globally (ARCHITECTURE.md V3 §V3.3/§V3.10). That's
          a backend contract change, flagged here rather than built now (owner said don't
          scope-creep). Linking to the global confusion mode is the reasonable "close enough"
          stand-in until that lands. */}
      <Link
        href="/review?mode=confusion"
        className="transition-standard mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-[var(--accent)] hover:text-[var(--accent-hover)]"
      >
        Тренировать похожие конструкции →
      </Link>
    </div>
  );
}

function GrammarRow({ item }: { item: GrammarWithProgressOut }) {
  return (
    <li>
      <Link
        href={`/grammar/${item.id}`}
        className="transition-standard flex items-center justify-between gap-4 rounded-xl border border-[var(--border)] bg-[var(--bg)]/40 px-5 py-4 hover:border-[var(--accent)]"
      >
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="jp-text text-lg font-semibold text-[var(--ink)]">
              {item.expression_clean}
            </span>
            <span className="jp-text text-sm text-[var(--ink-muted)]">{item.reading}</span>
            <span className="text-[10px] font-medium uppercase tracking-wide text-[var(--ink-faint)]">
              {item.level}
            </span>
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
  );
}

function MasteryBadge({ pct }: { pct: number }) {
  return (
    <span
      className="shrink-0 rounded-full border border-[var(--border)] bg-[var(--bg)] px-2.5 py-1 text-[11px] font-medium text-[var(--ink-muted)]"
      title="Доля освоенных конструкций"
    >
      {pct}% освоено
    </span>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className={`transition-standard h-3.5 w-3.5 shrink-0 text-[var(--ink-faint)] ${open ? "rotate-90" : ""}`}
      fill="none"
    >
      <path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
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
