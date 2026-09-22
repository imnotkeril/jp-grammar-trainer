"use client";

// Review session — ARCHITECTURE.md §8 / Phase 4 task 4.3.
// TODO(frontend-dev): implement the full loop per SPEC §8 acceptance flow:
//   session-length picker (5/10/20) -> api.startSession() -> QuestionCard per question ->
//   on select, api.submitAnswer() -> ContrastiveExplanation -> next question -> back to
//   dashboard when the session ends, with counters refreshed.
// This is a static shell so the scaffold boots end-to-end; no live state wiring yet.

import { useState } from "react";
import type { FuriganaMode } from "@/lib/types";

const SESSION_SIZES = [5, 10, 20] as const;

export default function ReviewPage() {
  const [sessionSize, setSessionSize] = useState<(typeof SESSION_SIZES)[number]>(10);
  const [furiganaMode] = useState<FuriganaMode>("by_level");

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-semibold">Review session</h1>
      <p className="text-sm text-neutral-500">Furigana mode: {furiganaMode}</p>
      <div className="flex gap-2">
        {SESSION_SIZES.map((size) => (
          <button
            key={size}
            type="button"
            onClick={() => setSessionSize(size)}
            aria-pressed={sessionSize === size}
            className="rounded-md border border-neutral-300 px-4 py-2 aria-pressed:border-blue-500 dark:border-neutral-700"
          >
            {size}
          </button>
        ))}
      </div>
      <p className="text-neutral-500">
        Session start not wired yet — see ARCHITECTURE.md Phase 4 task 4.3.
      </p>
    </main>
  );
}
