// Typed fetch client for the FastAPI backend. See ARCHITECTURE.md §8 for the endpoint list.
// TODO(frontend-dev, ARCHITECTURE.md Phase 4 task 4.1): wire NEXT_PUBLIC_API_BASE_URL once
// the backend is deployed; wrap fetch errors into a shared UI-friendly error type.

import type {
  AnswerRequest,
  AnswerResponse,
  GrammarDetailOut,
  GrammarLevel,
  GrammarListOut,
  GrammarListParams,
  GrammarRelationEdge,
  GrammarRelationOut,
  ReviewMode,
  SessionResponse,
  Stats,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API request failed: ${init?.method ?? "GET"} ${path} -> ${res.status}`);
  }
  return res.json() as Promise<T>;
}

function buildQuery(params?: GrammarListParams): string {
  if (!params) return "";
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  if (params.tag) search.set("tag", params.tag);
  if (params.level) search.set("level", params.level);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  // ARCHITECTURE.md V2 §V2.3 — {items, total} wrapper replaces MVP's bare array.
  // Default limit=205 offset=0 on the backend means an unparameterized call still returns
  // "everything", matching the list page's client-side search/filter approach (§V2.4).
  listGrammar: (params?: GrammarListParams): Promise<GrammarListOut> =>
    request(`/grammar${buildQuery(params)}`),

  getGrammar: (id: string): Promise<GrammarDetailOut> => request(`/grammar/${id}`),

  getGrammarRelations: (id: string): Promise<GrammarRelationOut[]> =>
    request(`/grammar/${id}/relations`),

  getAllGrammarRelations: (): Promise<GrammarRelationEdge[]> => request("/grammar/relations"),

  // ARCHITECTURE.md V3 §V3.6 — mode defaults to "due" server-side when omitted.
  // V4 §V4.4 — level is an additional opt-in filter, null/omitted = spans all levels.
  startSession: (size: 5 | 10 | 20, mode?: ReviewMode, level?: GrammarLevel): Promise<SessionResponse> =>
    request("/review/session", {
      method: "POST",
      body: JSON.stringify({
        size,
        ...(mode ? { mode } : {}),
        ...(level ? { level } : {}),
      }),
    }),

  submitAnswer: (body: AnswerRequest): Promise<AnswerResponse> =>
    request("/review/answer", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // V4 §V4.4 — level scopes every stat to that level's grammar_progress rows; omitted =
  // combined stats across all levels (unchanged existing behavior).
  getStats: (level?: GrammarLevel): Promise<Stats> =>
    request(`/stats${level ? `?level=${level}` : ""}`),
};
