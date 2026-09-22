// Shared loading/error presentation — used by Dashboard, Review, and Stats so a down/
// unreachable backend (expected while backend-dev's endpoints are still landing) never
// surfaces a raw fetch error or stack trace to the user.

interface LoadingBlockProps {
  label?: string;
}

export function LoadingBlock({ label = "Загрузка…" }: LoadingBlockProps) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-5 py-6 text-sm text-[var(--ink-muted)]">
      <span
        aria-hidden
        className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--border-strong)] border-t-[var(--accent)]"
      />
      <span>{label}</span>
    </div>
  );
}

interface ErrorBlockProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorBlock({
  message = "Не удалось связаться с сервером. Возможно, backend ещё не запущен.",
  onRetry,
}: ErrorBlockProps) {
  return (
    <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-5 py-5 text-sm text-[var(--error)]">
      <p>{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="transition-standard mt-3 rounded-md border border-[var(--error-border)] px-3 py-1.5 text-xs font-medium hover:bg-[var(--error-border)]/20"
        >
          Повторить
        </button>
      )}
    </div>
  );
}
