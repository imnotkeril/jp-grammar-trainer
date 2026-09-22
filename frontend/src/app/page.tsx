// Dashboard — ARCHITECTURE.md §8 / Phase 4 task 4.2.
// TODO(frontend-dev): fetch real stats via api.getStats() (client component + useEffect,
// or a server component once the backend has a stable deployed URL). Currently a static
// shell so the scaffold boots; wire the "Start Review" CTA to /review.

import Link from "next/link";
import DueCounter from "@/components/DueCounter";

export default function DashboardPage() {
  const placeholderDueCount = 0;

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-semibold">JP Grammar Trainer</h1>
      <DueCounter dueCount={placeholderDueCount} />
      <Link
        href="/review"
        className="rounded-md bg-neutral-900 px-6 py-3 text-center font-medium text-white transition hover:bg-neutral-700 dark:bg-white dark:text-neutral-900"
      >
        Start Review
      </Link>
      <Link href="/stats" className="text-center text-sm text-neutral-500 underline">
        View statistics
      </Link>
    </main>
  );
}
