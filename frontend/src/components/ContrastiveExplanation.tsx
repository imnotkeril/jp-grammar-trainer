import type { FuriganaMode } from "@/lib/types";
import FuriganaText from "./FuriganaText";

interface ContrastiveExplanationProps {
  isCorrect: boolean;
  sentenceFullHtml: string;
  explanationRu: string | null;
  furiganaMode: FuriganaMode;
}

export default function ContrastiveExplanation({
  isCorrect,
  sentenceFullHtml,
  explanationRu,
  furiganaMode,
}: ContrastiveExplanationProps) {
  return (
    <div
      className={`rounded-xl border p-6 ${
        isCorrect
          ? "border-[var(--success-border)] bg-[var(--success-bg)]"
          : "border-[var(--error-border)] bg-[var(--error-bg)]"
      }`}
    >
      <p
        className={`font-display text-lg font-semibold ${
          isCorrect ? "text-[var(--success)]" : "text-[var(--error)]"
        }`}
      >
        {isCorrect ? "Верно" : "Неверно"}
      </p>
      <FuriganaText
        html={sentenceFullHtml}
        mode={furiganaMode}
        className="jp-text mt-3 block text-lg leading-loose text-[var(--ink)]"
      />
      {explanationRu && (
        <p className="mt-4 border-t border-[var(--border)] pt-4 text-sm leading-relaxed text-[var(--ink-muted)]">
          {explanationRu}
        </p>
      )}
    </div>
  );
}
