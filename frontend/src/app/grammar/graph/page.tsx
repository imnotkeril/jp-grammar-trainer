"use client";

// Grammar relation graph — ARCHITECTURE.md "V2 Slice" §V2.4 (task V2.9).
// Fetches GET /grammar (node labels) + GET /grammar/relations (edges) once; layout + render
// happens in GrammarGraph.tsx (hand-rolled force-directed canvas, zero new deps, ADR-13).

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { GrammarRelationEdge, GrammarWithProgressOut } from "@/lib/types";
import { ErrorBlock, LoadingBlock } from "@/components/StatusBlocks";
import GrammarGraph from "@/components/GrammarGraph";

type LoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; items: GrammarWithProgressOut[]; edges: GrammarRelationEdge[] };

export default function GrammarGraphPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    // V4: same 205-item default-limit truncation bug as the grammar list page — request all
    // ~496 items across N3/N4/N2 explicitly, or the graph silently only shows N3 nodes.
    Promise.all([api.listGrammar({ limit: 1000 }), api.getAllGrammarRelations()])
      .then(([list, edges]) => setState({ status: "ready", items: list.items, edges }))
      .catch(() => setState({ status: "error" }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 px-4 py-10">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-semibold text-[var(--ink)]">Граф связей</h1>
          <p className="mt-1 text-sm text-[var(--ink-muted)]">
            Все конструкции и типы связей между ними
          </p>
        </div>
        <Link
          href="/grammar"
          className="transition-standard shrink-0 rounded-full border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm font-medium text-[var(--ink-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
        >
          ← Список
        </Link>
      </div>

      {state.status === "loading" && <LoadingBlock label="Строю граф…" />}
      {state.status === "error" && <ErrorBlock onRetry={load} />}
      {state.status === "ready" && state.items.length === 0 && (
        <p className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-8 text-center text-sm text-[var(--ink-muted)]">
          Нет данных для построения графа.
        </p>
      )}
      {state.status === "ready" && state.items.length > 0 && (
        <GrammarGraph items={state.items} edges={state.edges} />
      )}
    </main>
  );
}
