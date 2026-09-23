"use client";

// ARCHITECTURE.md V4 §V4.5 — segmented control for the global JLPT level, same visual/ARIA
// pattern as FuriganaModeToggle.tsx (radiogroup of pill buttons).

import type { LevelFilter } from "@/lib/types";

const OPTIONS: { value: LevelFilter; label: string }[] = [
  { value: "N3", label: "N3" },
  { value: "N4", label: "N4" },
  { value: "N2", label: "N2" },
  { value: "all", label: "Все" },
];

interface LevelSelectorProps {
  value: LevelFilter;
  onChange: (value: LevelFilter) => void;
  className?: string;
}

export default function LevelSelector({ value, onChange, className }: LevelSelectorProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Уровень JLPT"
      className={`inline-flex items-center gap-0.5 rounded-full border border-[var(--border)] bg-[var(--surface)] p-1 text-xs ${className ?? ""}`}
    >
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="radio"
          aria-checked={value === opt.value}
          onClick={() => onChange(opt.value)}
          className={`transition-standard whitespace-nowrap rounded-full px-2.5 py-1.5 font-medium ${
            value === opt.value
              ? "bg-[var(--accent)] text-[var(--accent-ink)]"
              : "text-[var(--ink-muted)] hover:text-[var(--ink)]"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
