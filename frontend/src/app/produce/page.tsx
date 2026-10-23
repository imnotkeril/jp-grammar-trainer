"use client";

// Sentence-production practice — offline, stateless. The learner sees the abstract pattern and
// the Russian translation of a seeded example, types their own Japanese sentence, gets an
// advisory "does it contain the construction" check, then compares with the model sentence
// and self-rates. Self-ratings live in this page's state only; nothing touches the SRS.

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { LevelFilter, ProductionCheckResult, ProductionMatch, ProductionPrompt } from "@/lib/types";
import { useFuriganaMode } from "@/lib/useFuriganaMode";
import { useLevel } from "@/lib/level-context";
import FuriganaModeToggle from "@/components/FuriganaModeToggle";
import FuriganaText from "@/components/FuriganaText";
import LevelSelector from "@/components/LevelSelector";
import { ErrorBlock, LoadingBlock } from "@/components/StatusBlocks";

const SIZES = [5, 10, 20] as const;
type Size = (typeof SIZES)[number];
type Rating = "good" | "almost" | "miss";
type Phase = "setup" | "starting" | "active" | "empty" | "summary";

const MATCH_MESSAGE: Record<ProductionMatch, { text: string; tone: "ok" | "warn" }> = {
  exact: { text: "Конструкция найдена в вашем предложении.", tone: "ok" },
  stem: { text: "Похоже на нужную конструкцию, но форма отличается — сравните с образцом.", tone: "warn" },
  none: { text: "Не вижу нужной конструкции — сравните с образцом.", tone: "warn" },
  empty: { text: "Предложение не введено.", tone: "warn" },
};

const RATINGS: { value: Rating; label: string }[] = [
  { value: "good", label: "Верно" },
  { value: "almost", label: "Почти" },
  { value: "miss", label: "Не получилось" },
];

export default function ProducePage() {
  const [furiganaMode, setFuriganaMode] = useFuriganaMode();
  const [headerLevel] = useLevel();
  const [size, setSize] = useState<Size>(5);
  const [level, setLevel] = useState<LevelFilter>("all");
  const [phase, setPhase] = useState<Phase>("setup");
  const [startError, setStartError] = useState(false);

  const [prompts, setPrompts] = useState<ProductionPrompt[]>([]);
  const [index, setIndex] = useState(0);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<ProductionCheckResult | undefined>(undefined);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState(false);
  const [ratings, setRatings] = useState<Rating[]>([]);
  const [rated, setRated] = useState(false);

  useEffect(() => {
    setLevel(headerLevel);
  }, [headerLevel]);

  const prompt = prompts[index];

  function start() {
    setPhase("starting");
    setStartError(false);
    api
      .startProductionSession(size, level === "all" ? undefined : level)
      .then((res) => {
        if (res.prompts.length === 0) {
          setPhase("empty");
          return;
        }
        setPrompts(res.prompts);
        setIndex(0);
        setAnswer("");
        setResult(undefined);
        setRatings([]);
        setRated(false);
        setPhase("active");
      })
      .catch(() => {
        setStartError(true);
        setPhase("setup");
      });
  }

  function check() {
    if (!prompt || checking) return;
    setChecking(true);
    setCheckError(false);
    api
      .checkProduction(prompt.grammar_id, answer)
      .then((res) => setResult(res))
      .catch(() => setCheckError(true))
      .finally(() => setChecking(false));
  }

  function rate(value: Rating) {
    setRatings((prev) => [...prev, value]);
    setRated(true);
  }

  function next() {
    if (index + 1 >= prompts.length) {
      setPhase("summary");
      return;
    }
    setIndex(index + 1);
    setAnswer("");
    setResult(undefined);
    setRated(false);
    setCheckError(false);
  }

  const good = ratings.filter((r) => r === "good").length;
  const almost = ratings.filter((r) => r === "almost").length;

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-10">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="font-display text-2xl font-semibold text-[var(--ink)]">Письмо</h1>
        <FuriganaModeToggle mode={furiganaMode} onChange={setFuriganaMode} className="self-start sm:self-auto" />
      </div>

      {phase === "setup" && (
        <div className="flex flex-col gap-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <p className="text-sm text-[var(--ink-muted)]">
            Составьте своё предложение с конструкцией по русскому переводу. Проверка работает офлайн: она
            ищет конструкцию в тексте, а оценку вы ставите сами, сравнив с образцом.
          </p>
          <p className="text-sm text-[var(--ink-muted)]">Сколько предложений?</p>
          <div className="flex gap-2">
            {SIZES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSize(s)}
                aria-pressed={size === s}
                className="transition-standard rounded-md border border-[var(--border)] px-5 py-2 font-medium text-[var(--ink)] aria-pressed:border-[var(--accent)] aria-pressed:bg-[var(--accent-soft)]"
              >
                {s}
              </button>
            ))}
          </div>
          <p className="mt-2 text-sm text-[var(--ink-muted)]">Уровень</p>
          <LevelSelector value={level} onChange={setLevel} />
          {startError && <ErrorBlock message="Не удалось начать сессию. Backend недоступен?" />}
          <button
            type="button"
            onClick={start}
            className="transition-standard mt-2 rounded-lg bg-[var(--accent)] px-6 py-3 font-medium text-[var(--accent-ink)] hover:bg-[var(--accent-hover)]"
          >
            Начать
          </button>
        </div>
      )}

      {phase === "starting" && <LoadingBlock label="Собираю задания…" />}

      {phase === "empty" && (
        <div className="flex flex-col gap-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-center">
          <p className="text-[var(--ink)]">Нет заданий для выбранного уровня.</p>
          <button type="button" onClick={() => setPhase("setup")} className="text-sm text-[var(--accent)] underline">
            Назад
          </button>
        </div>
      )}

      {phase === "active" && prompt && (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-[var(--ink-muted)]">
            Задание {index + 1} из {prompts.length} · {prompt.level}
          </p>

          <div className="flex flex-col gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
            <p className="text-sm font-medium uppercase tracking-wide text-[var(--ink-muted)]">Конструкция</p>
            <p className="jp-text text-xl font-semibold text-[var(--ink)]">{prompt.pattern_hint}</p>
            {prompt.meaning_hint && <p className="text-sm text-[var(--ink-muted)]">{prompt.meaning_hint}</p>}
            {prompt.formation_hints.length > 0 && (
              <p className="jp-text text-xs text-[var(--ink-faint)]">{prompt.formation_hints.join(" · ")}</p>
            )}
            <p className="mt-2 text-sm font-medium uppercase tracking-wide text-[var(--ink-muted)]">
              Переведите на японский
            </p>
            <p className="text-base text-[var(--ink)]">{prompt.meaning_ru}</p>
          </div>

          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            disabled={result !== undefined}
            rows={3}
            lang="ja"
            placeholder="日本語で入力…"
            className="jp-text w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 text-lg text-[var(--ink)] focus:border-[var(--accent)] focus:outline-none"
          />

          {checkError && <ErrorBlock message="Не удалось проверить. Попробуйте ещё раз." />}
          {checking && <LoadingBlock label="Проверяю…" />}

          {result === undefined && (
            <button
              type="button"
              onClick={check}
              disabled={checking}
              className="transition-standard rounded-lg bg-[var(--accent)] px-6 py-3 font-medium text-[var(--accent-ink)] hover:bg-[var(--accent-hover)] disabled:opacity-50"
            >
              Проверить
            </button>
          )}

          {result && (
            <div className="flex flex-col gap-4">
              <div
                className={`rounded-xl border p-4 text-sm ${
                  MATCH_MESSAGE[result.match].tone === "ok"
                    ? "border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success)]"
                    : "border-[var(--error-border)] bg-[var(--error-bg)] text-[var(--error)]"
                }`}
              >
                <p>{MATCH_MESSAGE[result.match].text}</p>
                {result.too_short && result.match !== "empty" && (
                  <p className="mt-1">Постарайтесь составить полное предложение, а не одну конструкцию.</p>
                )}
              </div>

              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
                <p className="text-sm font-medium uppercase tracking-wide text-[var(--ink-muted)]">Образец</p>
                <FuriganaText
                  html={result.model_sentence_html}
                  mode={furiganaMode}
                  className="jp-text mt-2 block text-lg leading-loose text-[var(--ink)]"
                />
                <p className="mt-3 text-sm text-[var(--ink-muted)]">Ваш вариант совпадает по смыслу и грамматике?</p>
                <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                  {RATINGS.map((r) => (
                    <button
                      key={r.value}
                      type="button"
                      onClick={() => rate(r.value)}
                      disabled={rated}
                      className="transition-standard flex-1 rounded-md border border-[var(--border)] px-4 py-2 font-medium text-[var(--ink)] hover:border-[var(--accent)] disabled:opacity-50"
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>

              {rated && (
                <button
                  type="button"
                  onClick={next}
                  className="transition-standard rounded-lg bg-[var(--accent)] px-6 py-3 font-medium text-[var(--accent-ink)] hover:bg-[var(--accent-hover)]"
                >
                  {index + 1 >= prompts.length ? "Завершить" : "Дальше"}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {phase === "summary" && (
        <div className="flex flex-col gap-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-center">
          <div>
            <p className="text-sm text-[var(--ink-muted)]">Сессия завершена</p>
            <p className="font-display mt-1 text-5xl font-semibold text-[var(--ink)]">
              {good}/{ratings.length}
            </p>
            <p className="mt-1 text-sm text-[var(--ink-muted)]">
              верно · {almost} почти · {ratings.length - good - almost} не получилось
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={() => setPhase("setup")}
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
      )}
    </main>
  );
}
