interface DueCounterProps {
  dueCount: number;
}

export default function DueCounter({ dueCount }: DueCounterProps) {
  const hasDue = dueCount > 0;
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-center">
      <p className="text-sm text-[var(--ink-muted)]">
        {hasDue ? "Готово к повторению" : "Повторений на сегодня нет"}
      </p>
      <p className="font-display mt-1 text-5xl font-semibold text-[var(--ink)]">{dueCount}</p>
      {!hasDue && (
        <p className="mt-2 text-xs text-[var(--ink-muted)]">
          Можно позаниматься новыми конструкциями — очередь никогда не пуста.
        </p>
      )}
    </div>
  );
}
