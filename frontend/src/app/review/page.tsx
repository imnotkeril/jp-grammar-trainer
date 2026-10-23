"use client";

// Review session — ARCHITECTURE.md §8 / Phase 4 task 4.3.
// Full loop per SPEC §8/§41-42: session-length picker -> api.startSession() -> question
// (sentence w/ blank + 4 options, furigana via FuriganaText) -> select an option ->
// api.submitAnswer() -> immediate contrastive explanation -> Next -> repeat -> summary ->
// back to Dashboard. Selecting an option submits immediately (no separate "submit" step) to
// keep per-question interaction snappy per SPEC §42 — no forced animations/delays anywhere
// in this flow.

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { AnswerResponse, LevelFilter, Question, ReviewMode } from "@/lib/types";
import { useFuriganaMode } from "@/lib/useFuriganaMode";
import { isLevelFilter } from "@/lib/level-context";
import FuriganaModeToggle from "@/components/FuriganaModeToggle";
import LevelSelector from "@/components/LevelSelector";
import QuestionCard from "@/components/QuestionCard";
import ContrastiveExplanation from "@/components/ContrastiveExplanation";
import { ErrorBlock, LoadingBlock } from "@/components/StatusBlocks";

const SESSION_SIZES = [5, 10, 20] as const;
type SessionSize = (typeof SESSION_SIZES)[number];

// ARCHITECTURE.md V3 §V3.3/§V3.10 — three practice entry points. "due" mixes in a small
// weak-point ratio server-side by default; the other two are dedicated modes.
const REVIEW_MODES: { value: ReviewMode; label: string; hint: string }[] = [
  { value: "due", label: "Обычное повторение", hint: "По расписанию SRS" },
  { value: "confusion", label: "Путаница", hint: "Часто путаемые конструкции" },
  { value: "weak_points", label: "Слабые места", hint: "Худшие по применению и различению" },
];

function isReviewMode(value: string | null): value is ReviewMode {
  return value === "due" || value === "confusion" || value === "weak_points";
}

interface HistoryEntry {
  question: Question;
  selectedOption: string;
  isCorrect: boolean;
}

type Phase = "setup" | "starting" | "active" | "empty" | "summary";

export default function ReviewPage() {
  // useSearchParams requires a Suspense boundary around any consumer (Next.js App Router).
  return (
    <Suspense fallback={<main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-10" />}>
      <ReviewPageInner />
    </Suspense>
  );
}

function ReviewPageInner() {
  const searchParams = useSearchParams();
  const [furiganaMode, setFuriganaMode] = useFuriganaMode();

  const [sessionSize, setSessionSize] = useState<SessionSize>(10);
  // Deep-linkable via ?mode= (e.g. a Dashboard/Stats "Слабые места" link) — ARCHITECTURE.md
  // V3 §V3.10. Falls back to "due" for a missing/invalid value.
  const [reviewMode, setReviewMode] = useState<ReviewMode>("due");
  // V4 §V4.5 — level rides along as one more optional field, same as mode did in V3.
  // Deep-linkable via ?level= (e.g. the Dashboard's "Начать повторение"/"Слабые места" links,
  // which append the currently-selected header level). Falls back to "all" (no filter).
  const [level, setLevel] = useState<LevelFilter>("all");
  // Deep-linkable via ?family=<grammar id> (the "Тренировать похожие конструкции" link on a
  // /grammar cluster card): scopes Confusion Practice to that relation family. Only honored
  // in confusion mode — switching the mode picker away drops the scope.
  const [familyId, setFamilyId] = useState<string | undefined>(undefined);
  const [phase, setPhase] = useState<Phase>("setup");
  const [startError, setStartError] = useState(false);

  const [questions, setQuestions] = useState<Question[]>([]);
  const [knownWords, setKnownWords] = useState<ReadonlySet<string>>(new Set());
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedOption, setSelectedOption] = useState<string | undefined>(undefined);
  const [answerResult, setAnswerResult] = useState<AnswerResponse | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(false);
  const [questionStartedAt, setQuestionStartedAt] = useState(0);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  const currentQuestion = questions[currentIndex];

  useEffect(() => {
    const fromQuery = searchParams.get("mode");
    if (isReviewMode(fromQuery)) {
      setReviewMode(fromQuery);
    }
    const familyFromQuery = searchParams.get("family");
    setFamilyId(familyFromQuery && isReviewMode(fromQuery) && fromQuery === "confusion" ? familyFromQuery : undefined);
    const levelFromQuery = searchParams.get("level");
    if (isLevelFilter(levelFromQuery)) {
      setLevel(levelFromQuery);
    }
  }, [searchParams]);

  function startSession(size: SessionSize, mode: ReviewMode, sessionLevel: LevelFilter, family?: string) {
    setSessionSize(size);
    setPhase("starting");
    setStartError(false);
    api
      .startSession(size, mode, sessionLevel === "all" ? undefined : sessionLevel, mode === "confusion" ? family : undefined)
      .then((res) => {
        if (res.questions.length === 0) {
          setPhase("empty");
          return;
        }
        setQuestions(res.questions);
        setKnownWords(new Set(res.known_words));
        setCurrentIndex(0);
        setSelectedOption(undefined);
        setAnswerResult(undefined);
        setHistory([]);
        setQuestionStartedAt(Date.now());
        setPhase("active");
      })
      .catch(() => {
        setStartError(true);
        setPhase("setup");
      });
  }

  function selectOption(optionKey: string) {
    if (submitting || selectedOption || !currentQuestion) return;
    setSelectedOption(optionKey);
    setSubmitting(true);
    setSubmitError(false);

    const responseTimeMs = Date.now() - questionStartedAt;

    api
      .submitAnswer({
        question_id: currentQuestion.id,
        selected_option: optionKey,
        response_time_ms: responseTimeMs,
      })
      .then((result) => {
        setAnswerResult(result);
        setSubmitting(false);
        setHistory((prev) => [
          ...prev,
          { question: currentQuestion, selectedOption: optionKey, isCorrect: result.is_correct },
        ]);
      })
      .catch(() => {
        setSubmitError(true);
        setSubmitting(false);
        setSelectedOption(undefined); // let them try again
      });
  }

  function goNext() {
    const nextIndex = currentIndex + 1;
    if (nextIndex >= questions.length) {
      setPhase("summary");
      return;
    }
    setCurrentIndex(nextIndex);
    setSelectedOption(undefined);
    setAnswerResult(undefined);
    setSubmitError(false);
    setQuestionStartedAt(Date.now());
  }

  function resetToSetup() {
    setPhase("setup");
    setQuestions([]);
    setCurrentIndex(0);
    setHistory([]);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-10">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="font-display text-2xl font-semibold text-[var(--ink)]">Повторение</h1>
        <FuriganaModeToggle mode={furiganaMode} onChange={setFuriganaMode} className="self-start sm:self-auto" />
      </div>

      {phase === "setup" && (
        <div className="flex flex-col gap-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <p className="text-sm text-[var(--ink-muted)]">Сколько вопросов?</p>
          <div className="flex gap-2">
            {SESSION_SIZES.map((size) => (
              <button
                key={size}
                type="button"
                onClick={() => setSessionSize(size)}
                aria-pressed={sessionSize === size}
                className="transition-standard rounded-md border border-[var(--border)] px-5 py-2 font-medium text-[var(--ink)] aria-pressed:border-[var(--accent)] aria-pressed:bg-[var(--accent-soft)]"
              >
                {size}
              </button>
            ))}
          </div>
          <p className="mt-2 text-sm text-[var(--ink-muted)]">Режим</p>
          <div className="flex flex-col gap-2 sm:flex-row">
            {REVIEW_MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                onClick={() => {
                  setReviewMode(m.value);
                  if (m.value !== "confusion") setFamilyId(undefined);
                }}
                aria-pressed={reviewMode === m.value}
                className="transition-standard flex-1 rounded-md border border-[var(--border)] px-4 py-2 text-left aria-pressed:border-[var(--accent)] aria-pressed:bg-[var(--accent-soft)]"
              >
                <span className="block font-medium text-[var(--ink)]">{m.label}</span>
                <span className="block text-xs text-[var(--ink-muted)]">{m.hint}</span>
              </button>
            ))}
          </div>

          {reviewMode === "confusion" && familyId && (
            <p className="flex items-center justify-between gap-3 rounded-md border border-[var(--accent)]/30 bg-[var(--accent-soft)] px-3 py-2 text-sm text-[var(--ink)]">
              <span>Только выбранная группа похожих конструкций</span>
              <button
                type="button"
                onClick={() => setFamilyId(undefined)}
                className="text-xs text-[var(--accent)] underline"
              >
                Все группы
              </button>
            </p>
          )}

          <p className="mt-2 text-sm text-[var(--ink-muted)]">Уровень</p>
          <LevelSelector value={level} onChange={setLevel} />

          {startError && <ErrorBlock message="Не удалось начать сессию. Backend недоступен?" />}
          <button
            type="button"
            onClick={() => startSession(sessionSize, reviewMode, level, familyId)}
            className="transition-standard mt-2 rounded-lg bg-[var(--accent)] px-6 py-3 font-medium text-[var(--accent-ink)] hover:bg-[var(--accent-hover)]"
          >
            Начать
          </button>
        </div>
      )}

      {phase === "starting" && <LoadingBlock label="Собираю вопросы…" />}

      {phase === "empty" && (
        <div className="flex flex-col gap-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-center">
          <p className="text-[var(--ink)]">Сейчас нечего повторять — все конструкции в порядке.</p>
          <Link href="/" className="text-sm text-[var(--accent)] underline">
            Вернуться на главную
          </Link>
        </div>
      )}

      {phase === "active" && currentQuestion && (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-[var(--ink-muted)]">
            Вопрос {currentIndex + 1} из {questions.length}
          </p>

          <QuestionCard
            question={currentQuestion}
            furiganaMode={furiganaMode}
            onSelect={selectOption}
            selectedOption={selectedOption}
            correctOption={answerResult?.correct_option}
            knownSurfaceForms={knownWords}
          />

          {submitting && <LoadingBlock label="Проверяю…" />}
          {submitError && <ErrorBlock message="Не удалось отправить ответ. Попробуйте ещё раз." />}

          {answerResult && (
            <>
              <ContrastiveExplanation
                isCorrect={answerResult.is_correct}
                sentenceFullHtml={answerResult.sentence_full_html}
                explanationRu={answerResult.explanation_ru}
                furiganaMode={furiganaMode}
                knownSurfaceForms={knownWords}
              />
              <button
                type="button"
                onClick={goNext}
                className="transition-standard rounded-lg bg-[var(--accent)] px-6 py-3 font-medium text-[var(--accent-ink)] hover:bg-[var(--accent-hover)]"
              >
                {currentIndex + 1 >= questions.length ? "Завершить" : "Дальше"}
              </button>
            </>
          )}
        </div>
      )}

      {phase === "summary" && (
        <SessionSummary history={history} onRestart={resetToSetup} />
      )}
    </main>
  );
}

interface SessionSummaryProps {
  history: HistoryEntry[];
  onRestart: () => void;
}

function SessionSummary({ history, onRestart }: SessionSummaryProps) {
  const total = history.length;
  const correct = history.filter((h) => h.isCorrect).length;
  const accuracy = total > 0 ? Math.round((correct / total) * 100) : 0;

  return (
    <div className="flex flex-col gap-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-center">
      <div>
        <p className="text-sm text-[var(--ink-muted)]">Сессия завершена</p>
        <p className="font-display mt-1 text-5xl font-semibold text-[var(--ink)]">
          {correct}/{total}
        </p>
        <p className="mt-1 text-sm text-[var(--ink-muted)]">{accuracy}% правильных ответов</p>
      </div>

      {history.some((h) => !h.isCorrect) && (
        <div className="text-left">
          <p className="mb-2 text-sm font-medium uppercase tracking-wide text-[var(--ink-muted)]">
            Стоит повторить
          </p>
          <ul className="flex flex-col gap-2">
            {history
              .filter((h) => !h.isCorrect)
              .map((h) => (
                <li
                  key={h.question.id}
                  className="jp-text rounded-md border border-[var(--error-border)] bg-[var(--error-bg)] px-3 py-2 text-left text-sm text-[var(--error)]"
                >
                  {h.question.options.find((o) => o.key === h.selectedOption)?.text ?? h.selectedOption}
                </li>
              ))}
          </ul>
        </div>
      )}

      <div className="flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          onClick={onRestart}
          className="transition-standard flex-1 rounded-lg border border-[var(--border)] px-6 py-3 font-medium text-[var(--ink)] hover:border-[var(--accent)]"
        >
          Ещё раз
        </button>
        <Link
          href="/"
          className="transition-standard flex-1 rounded-lg bg-[var(--accent)] px-6 py-3 font-medium text-[var(--accent-ink)] hover:bg-[var(--accent-hover)]"
        >
          На главную
        </Link>
      </div>
    </div>
  );
}
