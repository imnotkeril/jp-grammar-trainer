interface DueCounterProps {
  dueCount: number;
}

export default function DueCounter({ dueCount }: DueCounterProps) {
  return (
    <div className="rounded-lg border border-neutral-200 p-6 text-center dark:border-neutral-800">
      <p className="text-sm text-neutral-500">Due for review</p>
      <p className="text-4xl font-semibold">{dueCount}</p>
    </div>
  );
}
