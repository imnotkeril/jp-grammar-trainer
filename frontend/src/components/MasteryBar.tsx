import type { Stats } from "@/lib/types";

interface Segment {
  key: keyof Pick<Stats, "new_count" | "learning_count" | "review_count" | "mastered_count">;
  label: string;
  color: string;
}

const SEGMENTS: Segment[] = [
  { key: "new_count", label: "Новые", color: "bg-[var(--ink-faint)]" },
  { key: "learning_count", label: "Учатся", color: "bg-[var(--accent)]" },
  { key: "review_count", label: "Повторяются", color: "bg-[var(--success-border)]" },
  { key: "mastered_count", label: "Освоены", color: "bg-[var(--success)]" },
];

interface MasteryBarProps {
  stats: Stats;
}

export default function MasteryBar({ stats }: MasteryBarProps) {
  const total =
    stats.new_count + stats.learning_count + stats.review_count + stats.mastered_count || 1;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex h-3 w-full overflow-hidden rounded-full border border-[var(--border)] bg-[var(--surface)]">
        {SEGMENTS.map((segment) => {
          const value = stats[segment.key];
          const pct = (value / total) * 100;
          if (pct <= 0) return null;
          return (
            <div
              key={segment.key}
              className={`${segment.color} h-full`}
              style={{ width: `${pct}%` }}
              title={`${segment.label}: ${value}`}
            />
          );
        })}
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        {SEGMENTS.map((segment) => (
          <div key={segment.key} className="flex items-center gap-2">
            <span aria-hidden className={`${segment.color} h-2.5 w-2.5 rounded-full`} />
            <dt className="text-[var(--ink-muted)]">{segment.label}</dt>
            <dd className="ml-auto font-medium text-[var(--ink)]">{stats[segment.key]}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
