// Typed fetch client for the FastAPI backend. See ARCHITECTURE.md §8 for the endpoint list.
// TODO(frontend-dev, ARCHITECTURE.md Phase 4 task 4.1): wire NEXT_PUBLIC_API_BASE_URL once
// the backend is deployed; wrap fetch errors into a shared UI-friendly error type.

import type {
  AnswerRequest,
  AnswerResponse,
  GrammarItem,
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

export const api = {
  listGrammar: (): Promise<GrammarItem[]> => request("/grammar"),

  getGrammar: (id: string): Promise<GrammarItem> => request(`/grammar/${id}`),

  startSession: (size: 5 | 10 | 20): Promise<SessionResponse> =>
    request("/review/session", {
      method: "POST",
      body: JSON.stringify({ size }),
    }),

  submitAnswer: (body: AnswerRequest): Promise<AnswerResponse> =>
    request("/review/answer", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getStats: (): Promise<Stats> => request("/stats"),
};
