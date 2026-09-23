import Link from "next/link";

const NAV = [
  { href: "/", label: "Главная" },
  { href: "/review", label: "Повторение" },
  { href: "/grammar", label: "Грамматика" },
  { href: "/stats", label: "Статистика" },
] as const;

export default function AppHeader() {
  return (
    <header className="border-b border-[var(--border)] bg-[var(--surface)]/80 backdrop-blur">
      <div className="mx-auto flex max-w-2xl items-center justify-between gap-3 px-4 py-4">
        <Link href="/" className="flex shrink-0 items-baseline gap-2">
          <span className="jp-text font-display text-lg font-semibold text-[var(--ink)]">文法</span>
          <span className="hidden text-sm text-[var(--ink-muted)] sm:inline">JP Grammar · N3</span>
        </Link>
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
    </header>
  );
}
