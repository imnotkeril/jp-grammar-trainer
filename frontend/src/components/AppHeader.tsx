"use client";

import Link from "next/link";
import LevelSelector from "./LevelSelector";
import { useLevel } from "@/lib/level-context";

const NAV = [
  { href: "/", label: "Главная" },
  { href: "/review", label: "Повторение" },
  { href: "/grammar", label: "Грамматика" },
  { href: "/stats", label: "Статистика" },
] as const;

export default function AppHeader() {
  const [level, setLevel] = useLevel();

  return (
    <header className="border-b border-[var(--border)] bg-[var(--surface)]/80 backdrop-blur">
      <div className="mx-auto flex max-w-2xl flex-wrap items-center justify-between gap-3 px-4 py-4">
        <Link href="/" className="flex shrink-0 items-baseline gap-2">
          <span className="jp-text font-display text-lg font-semibold text-[var(--ink)]">文法</span>
          <span className="hidden text-sm text-[var(--ink-muted)] sm:inline">JP Grammar</span>
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <LevelSelector value={level} onChange={setLevel} />
          <nav className="flex gap-3 text-sm sm:gap-4">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-[var(--ink-muted)] transition-standard hover:text-[var(--accent)]"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </header>
  );
}
