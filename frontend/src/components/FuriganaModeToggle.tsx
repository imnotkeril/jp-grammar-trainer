"use client";

import type { FuriganaMode } from "@/lib/types";

const OPTIONS: { value: FuriganaMode; label: string }[] = [
  { value: "always", label: "Всегда" },
  { value: "by_level", label: "По уровню" },
  { value: "never", label: "Никогда" },
];

interface FuriganaModeToggleProps {
  mode: FuriganaMode;
  onChange: (mode: FuriganaMode) => void;
  className?: string;
}

export default function FuriganaModeToggle({ mode, onChange, className }: FuriganaModeToggleProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Режим фуриганы"
      className={`inline-flex items-center gap-0.5 rounded-full border border-[var(--border)] bg-[var(--surface)] p-1 text-xs ${className ?? ""}`}
    >
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="radio"
          aria-checked={mode === opt.value}
          onClick={() => onChange(opt.value)}
          className={`transition-standard whitespace-nowrap rounded-full px-2.5 py-1.5 font-medium ${
            mode === opt.value
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
