"use client";

// Grammar detail — ARCHITECTURE.md "V2 Slice" §V2.4 (task V2.8), structured per idea doc
// §35: meaning, formation, the Anki example sentence, and a "Сравнить с…" block grouping
// `relations` by relation_type (§V2.3's GrammarDetailOut).

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { GrammarDetailOut, GrammarRelationOut } from "@/lib/types";
import { RELATION_ORDER, RELATION_TYPE_LABELS, STATUS_COLORS, STATUS_LABELS, relationLabel } from "@/lib/grammar";
import { ErrorBlock, LoadingBlock } from "@/components/StatusBlocks";
import FuriganaText from "@/components/FuriganaText";
import FuriganaModeToggle from "@/components/FuriganaModeToggle";
import { useFuriganaMode } from "@/lib/useFuriganaMode";

type LoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; item: GrammarDetailOut };

export default function GrammarDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [furiganaMode, setFuriganaMode] = useFuriganaMode();

  const load = useCallback(() => {
    setState({ status: "loading" });
    api
      .getGrammar(id)
      .then((item) => setState({ status: "ready", item }))
      .catch(() => setState({ status: "error" }));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-10">
      <Link href="/grammar" className="text-sm text-[var(--ink-muted)] hover:text-[var(--accent)]">
        ← Все конструкции
      </Link>

      {state.status === "loading" && <LoadingBlock label="Загружаю конструкцию…" />}
      {state.status === "error" && <ErrorBlock onRetry={load} />}

      {state.status === "ready" && (
        <>
          <header className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-baseline gap-3">
                <h1 className="jp-text text-3xl font-semibold text-[var(--ink)]">
                  {state.item.expression_clean}
                </h1>
                <span className="jp-text text-lg text-[var(--ink-muted)]">{state.item.reading}</span>
              </div>
              <p className="mt-2 text-lg text-[var(--ink)]">{state.item.meaning_ru}</p>
            </div>
            <span
              className={`transition-standard shrink-0 rounded-full px-3 py-1 text-xs font-medium text-[var(--accent-ink)] ${STATUS_COLORS[state.item.status]}`}
            >
              {STATUS_LABELS[state.item.status]}
            </span>
          </header>

          <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
            <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-[var(--ink-muted)]">
              Значение и употребление
            </h2>
            <p className="whitespace-pre-line text-sm leading-relaxed text-[var(--ink)]">
              {state.item.pattern_text}
            </p>
          </section>

          {state.item.formation_rules.length > 0 && (
            <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
              <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-[var(--ink-muted)]">
                Образование
              </h2>
              <ul className="flex flex-col divide-y divide-[var(--border)]">
                {state.item.formation_rules.map((rule, i) => (
                  <li key={i} className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-baseline sm:gap-4">
                    <span className="w-32 shrink-0 text-xs font-medium uppercase tracking-wide text-[var(--ink-faint)]">
                      {rule.pos} · {rule.form_label}
                    </span>
                    <FuriganaText
                      html={rule.example_html}
                      mode={furiganaMode}
                      className="jp-text text-base text-[var(--ink)]"
                    />
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--ink-muted)]">
                Пример
              </h2>
              <FuriganaModeToggle mode={furiganaMode} onChange={setFuriganaMode} />
            </div>
            <FuriganaText
              html={state.item.expression_html}
              mode={furiganaMode}
              className="jp-text block text-lg leading-loose text-[var(--ink)]"
            />
          </section>

          <CompareWithSection relations={state.item.relations} />
        </>
      )}
    </main>
  );
}

// Grouping key: directional relation types (prerequisite/advanced_version) read differently
// depending on which side of the edge the viewed item sits on (ADR-11) — "Требует сначала
// выучить" is only correct from the *incoming* side, "Предшествует для" from the *outgoing*
// side. Grouping by type alone would mislabel one direction, so directional types group by
// (type, direction); symmetric types keep a single group per type.
function groupKey(rel: GrammarRelationOut): string {
  return rel.direction === "symmetric" ? rel.relation_type : `${rel.relation_type}|${rel.direction}`;
}

function groupHeading(rel: GrammarRelationOut): string {
  return rel.direction === "symmetric"
    ? RELATION_TYPE_LABELS[rel.relation_type]
    : relationLabel(rel.relation_type, rel.direction);
}

// Heuristic edges (no LLM key configured, see ARCHITECTURE.md ADR-12) carry a lot of weak
// "related" noise — a generic-particle overlap alone isn't worth showing as a comparison.
// Require a minimum signal strength before surfacing an edge in this user-facing list.
const MIN_DISPLAY_STRENGTH = 0.15;

function CompareWithSection({ relations }: { relations: GrammarRelationOut[] }) {
  const visible = relations.filter((rel) => rel.strength >= MIN_DISPLAY_STRENGTH);
  if (visible.length === 0) return null;

  const grouped = new Map<
    string,
    { heading: string; sortType: GrammarRelationOut["relation_type"]; items: GrammarRelationOut[] }
  >();
  for (const rel of visible) {
    const key = groupKey(rel);
    const entry = grouped.get(key);
    if (entry) {
      entry.items.push(rel);
    } else {
      grouped.set(key, { heading: groupHeading(rel), sortType: rel.relation_type, items: [rel] });
    }
  }

  const orderedKeys = Array.from(grouped.keys()).sort(
    (a, b) => RELATION_ORDER.indexOf(grouped.get(a)!.sortType) - RELATION_ORDER.indexOf(grouped.get(b)!.sortType),
  );

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
      <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-[var(--ink-muted)]">
        Сравнить с…
      </h2>
      <div className="flex flex-col gap-5">
        {orderedKeys.map((key) => {
          const group = grouped.get(key)!;
          return (
            <div key={key}>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--accent)]">
                {group.heading}
              </h3>
              <ul className="flex flex-col gap-2">
                {group.items.map((rel) => (
                  <li key={rel.related_grammar.id}>
                    <Link
                      href={`/grammar/${rel.related_grammar.id}`}
                      className="transition-standard flex items-start justify-between gap-3 rounded-lg border border-[var(--border)] px-4 py-3 hover:border-[var(--accent)]"
                    >
                      <div className="min-w-0">
                        <div className="flex items-baseline gap-2">
                          <span className="jp-text font-medium text-[var(--ink)]">
                            {rel.related_grammar.expression_clean}
                          </span>
                          <span className="jp-text text-xs text-[var(--ink-muted)]">
                            {rel.related_grammar.reading}
                          </span>
                        </div>
                        <p className="truncate text-xs text-[var(--ink-muted)]">
                          {rel.related_grammar.meaning_ru}
                        </p>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}
