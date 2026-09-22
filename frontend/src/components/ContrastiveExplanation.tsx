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
      className={`rounded-lg border p-6 ${
        isCorrect
          ? "border-green-500 bg-green-50 dark:bg-green-950"
          : "border-red-500 bg-red-50 dark:bg-red-950"
      }`}
    >
      <p className="font-semibold">{isCorrect ? "Верно" : "Неверно"}</p>
      <FuriganaText html={sentenceFullHtml} mode={furiganaMode} className="mt-2 block text-lg leading-loose" />
      {explanationRu && <p className="mt-3 text-sm text-neutral-600 dark:text-neutral-300">{explanationRu}</p>}
    </div>
  );
}
