"use client";

import type { FuriganaMode, Question } from "@/lib/types";
import FuriganaText from "./FuriganaText";

interface QuestionCardProps {
  question: Question;
  furiganaMode: FuriganaMode;
  onSelect: (optionKey: string) => void;
  selectedOption?: string;
  /** Set once the answer has been submitted — locks the options and reveals correctness. */
  correctOption?: string;
  /** V3 §V3.4 — only consulted when furiganaMode === "adaptive". */
  knownSurfaceForms?: ReadonlySet<string>;
}

export default function QuestionCard({
  question,
  furiganaMode,
  onSelect,
  selectedOption,
  correctOption,
  knownSurfaceForms,
}: QuestionCardProps) {
  const answered = correctOption !== undefined;

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
      <FuriganaText
        html={question.sentence_with_blank_html}
        mode={furiganaMode}
        knownSurfaceForms={knownSurfaceForms}
        className="jp-text block text-xl leading-loose text-[var(--ink)]"
      />
      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {question.options.map((option) => {
          const isSelected = selectedOption === option.key;
          const isCorrectOption = answered && correctOption === option.key;
          const isWrongSelection = answered && isSelected && correctOption !== option.key;

          let stateClasses = "border-[var(--border)] hover:border-[var(--accent)]";
          if (isCorrectOption) {
            stateClasses = "border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success)]";
          } else if (isWrongSelection) {
            stateClasses = "border-[var(--error-border)] bg-[var(--error-bg)] text-[var(--error)]";
          } else if (isSelected) {
            stateClasses = "border-[var(--accent)]";
          }

          return (
            <button
              key={option.key}
              type="button"
              disabled={answered}
              onClick={() => onSelect(option.key)}
              aria-pressed={isSelected}
              className={`transition-standard jp-text rounded-md border px-4 py-3 text-left disabled:cursor-default ${stateClasses}`}
            >
              <span className="mr-2 font-sans text-[var(--ink-faint)]">{option.key}</span>
              {option.text}
            </button>
          );
        })}
      </div>
    </div>
  );
}
