"use client";

import type { FuriganaMode, Question } from "@/lib/types";
import FuriganaText from "./FuriganaText";

// TODO(frontend-dev, ARCHITECTURE.md Phase 4 task 4.3): wire onSelect into
// api.submitAnswer(), disable options after answering, show correct/incorrect styling.

interface QuestionCardProps {
  question: Question;
  furiganaMode: FuriganaMode;
  onSelect: (optionKey: string) => void;
  selectedOption?: string;
}

export default function QuestionCard({
  question,
  furiganaMode,
  onSelect,
  selectedOption,
}: QuestionCardProps) {
  return (
    <div className="rounded-lg border border-neutral-200 p-6 dark:border-neutral-800">
      <FuriganaText
        html={question.sentence_with_blank_html}
        mode={furiganaMode}
        className="text-xl leading-loose"
      />
      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {question.options.map((option) => (
          <button
            key={option.key}
            type="button"
            onClick={() => onSelect(option.key)}
            aria-pressed={selectedOption === option.key}
            className="rounded-md border border-neutral-300 px-4 py-3 text-left transition hover:border-neutral-500 aria-pressed:border-blue-500 dark:border-neutral-700"
          >
            <span className="mr-2 font-mono text-neutral-400">{option.key}</span>
            {option.text}
          </button>
        ))}
      </div>
    </div>
  );
}
