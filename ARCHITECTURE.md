# ARCHITECTURE.md — Japanese Grammar Retrieval Trainer

Status: draft v1 · Basis: `SPEC.md` (approved) · Author: architect agent · Date: 2026-09-22

Этот документ фиксирует конкретную архитектуру, схему БД, пайплайны и taskplan для MVP,
описанного в `SPEC.md`. Ключевые решения по неоднозначностям, которые ТЗ явно не
разруливает, помечены **[ADR]** с обоснованием — владелец в моменте недоступен, решения
приняты автономно и прагматично, без блокировки.

---

## 1. System overview

```
┌─────────────────────┐        HTTPS/JSON        ┌──────────────────────────┐
│  Next.js PWA         │ ───────────────────────▶ │  FastAPI backend          │
│  (Vercel)             │ ◀─────────────────────── │  (Fly.io/Railway/Render*) │
│  App Router, TS,      │                          │  Python 3.12, uv          │
│  Tailwind, service    │                          │  SQLAlchemy + Alembic     │
│  worker (PWA)         │                          │  BackgroundTasks (gen)    │
└─────────────────────┘                          └───────────┬──────────────┘
                                                               │
                                                    ┌──────────▼───────────┐
                                                    │  Postgres (Supabase) │
                                                    └──────────┬───────────┘
                                                               │
                                        ┌──────────────────────┼──────────────────────┐
                                        │                                              │
                              ┌─────────▼─────────┐                        ┌───────────▼───────────┐
                              │  LLM abstraction    │                        │  Seed importer (uv    │
                              │  OpenAI adapter      │                        │  script, one-shot,     │
                              │  Anthropic adapter    │                        │  reads Anki JSON)     │
                              └───────────────────────┘                        └────────────────────────┘
```

**[ADR-1] Backend hosting.** SPEC §7 says "Vercel (frontend) + Supabase (Postgres)" but
does not name a Python host — Vercel's Python runtime is serverless-function-shaped and a
poor fit for a stateful FastAPI app with BackgroundTasks (cold starts kill in-flight
generation jobs). Decision: **Supabase for Postgres only**; FastAPI runs as a normal
long-lived process on any container host chosen at deploy time (Railway/Fly.io/Render —
devops agent's call at ship time, all three take `Dockerfile` uv images unmodified). Locally
it's just `uv run uvicorn`. This keeps frontend on Vercel exactly as spec'd and doesn't
lock in a host prematurely for a personal tool. Noted for devops.

**[ADR-2] No Redis/worker for MVP**, per SPEC §7: generation batches run via FastAPI
`BackgroundTasks` triggered synchronously inside the request that detects a shortage. No
job queue, no retries-with-backoff infra — acceptable failure mode for personal tool: if a
generation call fails, the endpoint that triggered it just logs and the next review-session
start retries the trigger. Upgrade path: swap `BackgroundTasks` call for an RQ/Celery enqueue
behind the same interface (`app/services/generation/trigger.py`) if load grows.

**[ADR-3] No auth for MVP.** No `User` table. Every row belongs implicitly to the single
owner. If/when multi-user is needed (not planned), add `owner_id` columns — schema below
already leaves them nullable-free but isolated in a single migration-friendly place (all
FKs point to `grammar_id`, not to a user), so adding a `user_id` later is one migration, not
a redesign.

---

## 2. Repo layout

Per `folders.md` — separate `frontend/` and `backend/` service folders at repo root.

```
JP Grammar app/
├── SPEC.md
├── ARCHITECTURE.md
├── data/seed/n3_grammar_anki_export.json
├── backend/
│   ├── pyproject.toml
│   ├── .env.example
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 0001_initial_schema.py
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── grammar.py
│   │   │   ├── grammar_progress.py
│   │   │   ├── question.py
│   │   │   └── question_attempt.py
│   │   ├── schemas/            # Pydantic request/response models
│   │   │   ├── __init__.py
│   │   │   ├── grammar.py
│   │   │   ├── review.py
│   │   │   └── stats.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── grammar.py       # GET /grammar, /grammar/{id}
│   │   │   ├── review.py        # POST /review/session, POST /review/answer
│   │   │   └── stats.py         # GET /stats
│   │   ├── services/
│   │   │   ├── srs.py           # scheduling algorithm (pure functions)
│   │   │   ├── distractors.py   # 4-choice distractor selection
│   │   │   ├── furigana.py      # ruby-markup rendering modes
│   │   │   └── generation/
│   │   │       ├── __init__.py
│   │   │       ├── provider.py      # LLMProvider protocol
│   │   │       ├── openai_adapter.py
│   │   │       ├── anthropic_adapter.py
│   │   │       ├── prompts.py
│   │   │       ├── validate.py
│   │   │       └── trigger.py       # batch-shortage detection + BackgroundTasks hook
│   │   └── scripts/
│   │       └── seed_import.py   # reads data/seed/*.json → Grammar rows
│   └── tests/
│       ├── test_srs.py
│       ├── test_seed_import.py
│       └── test_generation_validate.py
└── frontend/
    ├── package.json
    ├── next.config.ts
    ├── tsconfig.json
    ├── tailwind.config.ts
    ├── postcss.config.mjs
    ├── public/
    │   ├── manifest.webmanifest
    │   ├── icons/icon-192.png
    │   └── icons/icon-512.png
    └── src/
        ├── app/
        │   ├── layout.tsx
        │   ├── page.tsx              # Dashboard
        │   ├── review/page.tsx       # Review session
        │   ├── stats/page.tsx
        │   └── api/                  # (none on MVP — all data via backend FastAPI)
        ├── components/
        │   ├── FuriganaText.tsx      # renders ruby markup w/ toggle modes
        │   ├── QuestionCard.tsx
        │   ├── DueCounter.tsx
        │   └── ContrastiveExplanation.tsx
        ├── lib/
        │   ├── api.ts                # typed fetch client to backend
        │   └── types.ts
        └── styles/globals.css
```

---

## 3. Database schema (Postgres, Supabase)

Concretized from SPEC §5. Design notes:

- `formation_rules` stored as **jsonb array** of `{pos, form_label, example_html}` — one
  entry per line parsed from `connection_formation` (see §4 parsing below), not raw text,
  so the frontend can render formation tables without re-parsing HTML client-side.
- `expression_html` kept verbatim (source of truth for furigana rendering — see §5).
- `tags` is `text[]`; per SPEC §9 risk, Anki tags in the real export are **empty strings**
  (`"tags": ""` in every sampled row) — confirmed during read of the seed file. **[ADR-4]**
  MVP does **not** attempt LLM-based auto-tagging/categorization (that's explicitly V2 per
  SPEC §71 "lesson-based curriculum" / grammar categories). `tags` column exists and is
  populated as `{}` (empty array) for all 205 rows; distractor selection (§6 below) therefore
  uses pure random sampling, not tag-similarity, exactly as SPEC §6 already specifies as the
  MVP fallback.

```sql
-- 0001_initial_schema.py (Alembic) target DDL

CREATE TABLE grammar (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_note_id      BIGINT UNIQUE NOT NULL,        -- Anki note_id, for idempotent re-import
    expression_html     TEXT NOT NULL,                  -- original <ruby>/<rt>/<b> markup
    expression_clean    TEXT NOT NULL,                  -- plain JP, no markup
    reading             TEXT NOT NULL,                  -- kana reading, <b> around target
    meaning_ru          TEXT NOT NULL,
    pattern_text        TEXT NOT NULL,                  -- raw "Паттерн: ... / Значение: ..."
    formation_rules     JSONB NOT NULL DEFAULT '[]',    -- parsed [{pos, form_label, example_html}]
    level               TEXT NOT NULL DEFAULT 'N3',
    tags                TEXT[] NOT NULL DEFAULT '{}',
    target_construction TEXT NOT NULL,                  -- text inside <b> in expression_html (e.g. "うちに")
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_grammar_level ON grammar (level);
CREATE INDEX ix_grammar_tags ON grammar USING GIN (tags);

CREATE TYPE grammar_status AS ENUM ('new', 'learning', 'review', 'mastered');

CREATE TABLE grammar_progress (
    grammar_id          UUID PRIMARY KEY REFERENCES grammar(id) ON DELETE CASCADE,
    status               grammar_status NOT NULL DEFAULT 'new',
    first_seen           TIMESTAMPTZ,
    last_reviewed        TIMESTAMPTZ,
    next_review          TIMESTAMPTZ NOT NULL DEFAULT now(),  -- due immediately when new
    interval_days        INTEGER NOT NULL DEFAULT 0,
    interval_step        INTEGER NOT NULL DEFAULT 0,          -- index into FIXED_INTERVALS
    repetitions           INTEGER NOT NULL DEFAULT 0,
    lapses                INTEGER NOT NULL DEFAULT 0,
    recall_score          REAL NOT NULL DEFAULT 0,             -- rolling accuracy, 0..1
    application_score     REAL NOT NULL DEFAULT 0,             -- placeholder, V2-ready
    discrimination_score  REAL NOT NULL DEFAULT 0,             -- placeholder, V2-ready
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_progress_next_review ON grammar_progress (next_review);
CREATE INDEX ix_progress_status ON grammar_progress (status);

CREATE TYPE question_source AS ENUM ('seed', 'ai_generated');
CREATE TYPE validation_status AS ENUM ('pending', 'valid', 'rejected');

CREATE TABLE question (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grammar_id                 UUID NOT NULL REFERENCES grammar(id) ON DELETE CASCADE,
    question_type               TEXT NOT NULL DEFAULT 'fill_in_blank_4choice',
    sentence_with_blank_html    TEXT NOT NULL,          -- ruby-preserving, target replaced by ___
    sentence_full_html          TEXT NOT NULL,           -- for post-answer reveal
    options                      JSONB NOT NULL,          -- [{"key":"A","text":"..."}, ...]
    correct_option               TEXT NOT NULL,           -- "A".."D"
    explanation_ru               TEXT,                    -- contrastive explanation shown after answer
    source                        question_source NOT NULL,
    generation_model               TEXT,                   -- e.g. "gpt-4o-mini" / "claude-3-5-haiku"
    generation_prompt_version       TEXT,
    validation_status                validation_status NOT NULL DEFAULT 'valid',
    used_count                        INTEGER NOT NULL DEFAULT 0,   -- for "unused questions" shortage check
    dedup_hash                         TEXT,                        -- normalized sentence hash, unique per grammar
    created_at                          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_question_grammar ON question (grammar_id);
CREATE INDEX ix_question_shortage ON question (grammar_id, validation_status, used_count);
CREATE UNIQUE INDEX uq_question_dedup ON question (grammar_id, dedup_hash) WHERE dedup_hash IS NOT NULL;

CREATE TABLE question_attempt (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id          UUID NOT NULL REFERENCES question(id) ON DELETE CASCADE,
    grammar_id            UUID NOT NULL REFERENCES grammar(id) ON DELETE CASCADE,
    selected_option        TEXT NOT NULL,
    correct_option          TEXT NOT NULL,
    is_correct               BOOLEAN NOT NULL,
    response_time_ms          INTEGER,
    error_type                 TEXT,                    -- null | "wrong_form" | "wrong_meaning" | "guess" (freeform for MVP)
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_attempt_grammar ON question_attempt (grammar_id);
CREATE INDEX ix_attempt_question ON question_attempt (question_id);
```

**[ADR-5]** `grammar_progress` uses `grammar_id` as its own primary key (1:1 with `grammar`,
row created at seed-import time for every grammar item with `status='new'`) rather than a
separate surrogate id — simpler joins, and MVP never needs more than one progress record per
item (no multi-user).

---

## 4. Seed import mapping (Anki JSON → `grammar` table)

Source fields (confirmed by reading `data/seed/n3_grammar_anki_export.json`, 205 entries):
`note_id`, `expression_html`, `expression_clean`, `reading`, `meaning_ru`, `pattern`,
`connection_formation`, `tags`.

| Anki field | → DB column | Transform |
|---|---|---|
| `note_id` | `source_note_id` | as-is (bigint) |
| `expression_html` | `expression_html` | as-is (verbatim ruby markup) |
| `expression_clean` | `expression_clean` | as-is |
| `reading` | `reading` | as-is |
| `meaning_ru` | `meaning_ru` | as-is |
| `pattern` | `pattern_text` | as-is |
| — | `target_construction` | extracted from `expression_html`: text inside `<b>...</b>` (regex `<b>(.*?)</b>`), stripped of any nested `<ruby>` tags to get plain kana/kanji. Falls back to parsing the bold span in `reading` if `expression_html` has none. |
| `connection_formation` | `formation_rules` (jsonb) | parsed line-by-line (see below) |
| `tags` | `tags` | Anki tag string split on whitespace → `text[]`; empty string → `{}` (confirmed: all sampled rows are `""`) |
| — | `level` | hardcoded `"N3"` (whole deck is N3 per SPEC) |

**`formation_rules` parsing.** `connection_formation` is `\n`-separated lines of the shape
`<pos label>→<ruby-marked-up example>`, e.g. `гл.ている→<ruby>食べ<rt>たべ</rt></ruby>ているうちに`.
Import script splits on `\n`, then on the first `→`, producing:
```json
{"pos": "гл.ている", "form_label": "гл.ている", "example_html": "<ruby>食べ<rt>たべ</rt></ruby>ているうちに"}
```
Lines that don't contain `→` are skipped and logged (defensive — don't hard-fail import on
one malformed row out of 205).

**[ADR-6] Known data-quality issue, confirmed during scaffolding (broader than first
suspected).** Row `note_id=1775898451281` (`間` / あいだ item) has malformed
`expression_html`: the `<rt>` tag content bleeds into following text —
`<ruby><b>間</b><rt>あいだ、こ</rt></ruby>、<ruby>子<rt>どもたちはテレビをみていた。</rt></ruby>` — a
mis-scoped ruby span. Building the seed-import script and running it against the real 205-row
file surfaced that this is **not** an isolated one-off: **9 of 205 rows** have a `<rt>` span
whose payload contains stray Latin text or a nested tag (e.g. `'ものvs<b>こと</b>の違い'`,
`'よなかゆきがふったんですね。それで、きのうのよるあんな'`) — an automated heuristic
(nested-tag/Latin-text/length>25) catches these reliably. Row 1775898451281 (the one that
first surfaced the issue) bleeds *pure-kana* text into its `<rt>` (`'あいだ、こ'`), which is
visually wrong but indistinguishable from a legitimate multi-morpheme kana reading by the
heuristic, so it isn't auto-flagged — noted here for completeness, not worth a bespoke
detector for one extra row. Almost certainly the same class of Anki
rich-text-editor artifact (a `<b>` or comparison text typed *inside* an open ruby-reading
field instead of after it), not systematic corruption of the whole deck (spot-checked: the
other 194 rows are clean; plain kana readings containing `、`/`。` as morpheme separators are
common and *not* flagged as errors — only Latin letters, nested tags, or implausibly long
(>25 char) payloads count as broken). Decision: **do not hand-fix in the JSON.** The
seed-import script runs a defensive pass (`check_rt_payloads_are_kana`) and collects every
flagged row into an import report (`backend/app/scripts/seed_import_report.json`,
`type: "malformed_rt_payload"`) for the owner to spot-check later; import proceeds
regardless — nothing on MVP blocks on perfect furigana, and `expression_clean` (used for
question-generation prompts, §7.3) is unaffected since it carries no markup at all. Frontend
rendering (§5) is robust to this: `<rt>` with stray text just renders slightly odd ruby
text on 11 of 205 items, not a crash or data-loss.

**[ADR-6b] Addendum, found while scaffolding.** 3 of 205 rows (`note_id` 1775898451577,
1775898451579, 1775898451653 — all "〜と・〜たら" and "文の組み立て" pattern variants) have **no**
`<b>...</b>` span at all in either `expression_html` or `reading`, so `target_construction`
extraction yields `""` for them. Same treatment as ADR-6: import proceeds, `seed_import.py`
flags these note_ids in its report (`type: "no_target_construction_found"`) rather than
failing the batch or guessing at a fix. Downstream effect: these 3 items' distractor
generation (§7.5) and AI-generation grammar-fit validation (§7.4) can't rely on
`target_construction` and should treat an empty value as "skip the deterministic grammar-fit
check, don't block". Covered by `tests/test_seed_import.py::test_all_205_real_rows_parse_without_exception`.

---

## 5. Furigana rendering — MVP approach

SPEC §4.6: toggle `Always / Never / By-level`. Source already carries `<ruby><rt>` markup
authored by the owner in Anki — **reuse it, don't rebuild a furigana engine.**

- `expression_html` / example sentence HTML is rendered through a small React component
  (`FuriganaText.tsx`) that receives the raw HTML string and the toggle mode:
  - **Always**: render `dangerouslySetInnerHTML` as-is (ruby always visible — browsers
    natively support `<ruby><rt>`, zero extra work).
  - **Never**: strip all `<rt>...</rt>` content (regex, done once client-side or
    server-side at serialization) before render, keeping the base kanji text and the `<b>`
    emphasis on the target construction.
  - **By-level** (default, per SPEC): since MVP has only N3 content and no `UserVocabulary`
    tracking (that's V2 adaptive furigana), "by level" degrades to a static per-word-type
    heuristic — **[ADR-7]**: show furigana ruby only on kanji compounds *outside* the
    grammar's own target construction (the target itself, inside `<b>`, is what the user is
    being tested on and should stay furigana-free to keep them reading the kanji, matching
    the pedagogical intent of "retrieval" trainer — you shouldn't get the reading of the
    tested pattern for free). Concretely: keep `<rt>` for every `<ruby>` block **except**
    ones nested inside `<b>...</b>`. This needs no new data, no per-user vocab state, and is
    a straightforward DOM/regex transform. Documented as a heuristic that will be replaced
    by true adaptive-per-word furigana in V2 (SPEC §72).
- All three modes are pure functions over the stored HTML — no new DB fields, no
  server-side rendering variants stored. `sentence_with_blank_html` / `sentence_full_html`
  on `question` follow the same rule for AI-generated sentences (the generation prompt is
  asked to return ruby-marked-up HTML in the same `<ruby><rt>` shape, see §7).

---

## 6. SRS scheduling algorithm (MVP, fixed intervals)

Per SPEC §4.4 / idea doc §6: fixed steps `0 / 1 / 3 / 7 / 14 / 30 / 60 / 120` days, error
shortens interval. Concretized as pure functions in `backend/app/services/srs.py`:

```python
FIXED_INTERVALS_DAYS: list[int] = [0, 1, 3, 7, 14, 30, 60, 120]

def schedule_next(
    progress: GrammarProgressState,
    is_correct: bool,
    now: datetime,
) -> GrammarProgressState:
    """Pure function: current progress + attempt result -> new progress state."""
    if is_correct:
        next_step = min(progress.interval_step + 1, len(FIXED_INTERVALS_DAYS) - 1)
        repetitions = progress.repetitions + 1
        lapses = progress.lapses
    else:
        # error -> shorten: drop back 2 steps (floor at 0), not fully reset to 0.
        # A single slip on an otherwise-mastered item shouldn't nuke months of progress;
        # dropping 2 steps still meaningfully increases review frequency (SRS §4.4 intent).
        next_step = max(progress.interval_step - 2, 0)
        repetitions = 0
        lapses = progress.lapses + 1

    interval_days = FIXED_INTERVALS_DAYS[next_step]
    status = derive_status(next_step, repetitions, lapses)

    return GrammarProgressState(
        status=status,
        interval_step=next_step,
        interval_days=interval_days,
        repetitions=repetitions,
        lapses=lapses,
        last_reviewed=now,
        next_review=now + timedelta(days=interval_days),
        recall_score=rolling_accuracy(progress.recall_score, is_correct),
    )

def derive_status(interval_step: int, repetitions: int, lapses: int) -> GrammarStatus:
    if repetitions == 0 and interval_step == 0:
        return "new" if lapses == 0 else "learning"
    if interval_step <= 1:
        return "learning"
    if interval_step < len(FIXED_INTERVALS_DAYS) - 1:
        return "review"
    return "mastered"   # reached the 120-day step

def rolling_accuracy(prev: float, is_correct: bool, alpha: float = 0.2) -> float:
    """Exponential moving average, cheap proxy for recall_score. alpha=0.2 ~ last ~5 attempts weighted."""
    return prev + alpha * ((1.0 if is_correct else 0.0) - prev)
```

**[ADR-8] Error-shortening rule.** SPEC says "error → сократить интервал" without a formula.
Decision: drop back **2 steps** (not reset to 0) on a wrong answer. Rationale: full reset to
0 on every slip is punishing for an item at step 6 (60d) that's otherwise well-learned and
would flood the queue; industry SRS tools (Anki's own lapse handling) use a similar
partial-regression pattern rather than hard reset. `new`/`review`/`mastered` status is
*derived* from `interval_step`/`repetitions`/`lapses`, not stored independently, to avoid
drift.

Applied inside `POST /review/answer`: read current `grammar_progress` row → call
`schedule_next` → persist.

---

## 7. AI generation pipeline (concretized)

Per SPEC §6. Trigger, provider shape, validation, dedup made concrete:

### 7.1 Trigger
- On `POST /review/session` (session start), for every grammar item selected into the
  session, count `question WHERE grammar_id = X AND validation_status = 'valid' AND
  used_count < 1` (an "unused" question — MVP treats "unused" as never-served rather than
  tracking per-session history, simplest correct interpretation of SPEC §6's "unused
  questions").
- If count `< N` (config `GENERATION_SHORTAGE_THRESHOLD`, default `5`, per SPEC), enqueue a
  `BackgroundTasks.add_task(generate_batch_for_grammar, grammar_id, batch_size=15)` — fire
  after the response is sent, doesn't block the review session from starting (seed questions
  or whatever unused ones already exist are served immediately; new ones land in time for
  the *next* session).

### 7.2 Provider abstraction
```python
# app/services/generation/provider.py
class LLMProvider(Protocol):
    async def generate_sentences(self, prompt: GenerationPrompt) -> list[RawGeneratedSentence]: ...

# config.py
LLM_PROVIDER: Literal["openai", "anthropic"] = env("LLM_PROVIDER", default="anthropic")
OPENAI_API_KEY: str | None = env("OPENAI_API_KEY", default=None)
ANTHROPIC_API_KEY: str | None = env("ANTHROPIC_API_KEY", default=None)
```
Adapter chosen by `LLM_PROVIDER` at startup; factory raises a clear config error only if the
*selected* provider's key is missing — the other provider's key being absent is fine
(SPEC §9: "если только один под рукой... молча не звать другой" — literally: never call the
unconfigured provider, never even check its key).

Both adapters implement the same prompt→structured-output contract using each SDK's native
structured output / tool-calling (OpenAI: `response_format=json_schema`; Anthropic: forced
tool-use with a matching JSON schema) — **not** free-text parsing, to avoid brittle parsing
across two different model families. Same JSON schema for both:
```json
{"sentences": [{"sentence_with_blank_html": "...", "sentence_full_html": "...",
                "correct_answer_text": "...", "explanation_ru": "..."}]}
```

### 7.3 Prompt shape (`prompts.py`)
One shared prompt template, provider-agnostic (only the SDK call differs):
```
System: You are a Japanese N3 grammar exercise writer for a Russian-speaking learner.
User:
  Grammar point: {pattern_text}
  Target construction: {target_construction}
  Formation rules: {formation_rules as bullet list}
  Existing example (for style/level calibration, do not repeat): {expression_clean}
  Already-generated sentences for this grammar point (avoid near-duplicates): {existing_sentences[:20]}

  Generate {batch_size} NEW natural N3-level Japanese sentences that each correctly use
  "{target_construction}". For each sentence return:
  - sentence_full_html: the full sentence with <ruby><rt> furigana on kanji compounds
    (same markup convention as the example), and the target construction wrapped in <b>...</b>
  - sentence_with_blank_html: same sentence with the target construction replaced by "___"
  - correct_answer_text: the plain text that fills the blank
  - explanation_ru (2-3 sentences, Russian): why this construction fits here, contrasted
    with a commonly confused alternative construction if relevant.
  Vary sentence topic/register. Do not reuse the existing example's scenario.
```

### 7.4 Validation (`validate.py`) — MVP simplified per SPEC §6
1. **Structural**: response matches JSON schema (enforced by structured-output call itself;
   reject batch item if provider still returns malformed JSON).
2. **Grammar-fit check**: `target_construction` (plain text, ruby stripped) must literally
   appear inside `sentence_full_html`'s de-ruby'd text — cheap deterministic check, catches
   the model silently dropping/mis-forming the target. Fail → `validation_status='rejected'`.
3. **Duplicate check**: normalize `sentence_full_html` → strip HTML/ruby → strip
   punctuation/whitespace → lowercase → SHA-256 → `dedup_hash`. Insert with `ON CONFLICT
   (grammar_id, dedup_hash) DO NOTHING` (unique index already defined in schema). **[ADR-9]**
   MVP uses exact-normalized-string dedup, not embeddings — SPEC §6 offers both
   ("embedding или строгое string-similarity"); embeddings mean an extra API call + a vector
   column/index for marginal benefit at 15-sentences-per-batch scale. Revisit if near-dupes
   (same sentence, different particle) turn out common in practice.
4. Batch items passing 2+3 → inserted as `question(source='ai_generated',
   validation_status='valid')`. Items failing → still inserted with `validation_status='rejected'`
   for later inspection (cheap audit trail) but never selected for serving (`services/review.py`
   query always filters `validation_status='valid'`).

### 7.5 Distractors (`distractors.py`)
Per SPEC §6/MVP: 3 random other N3 grammar items' `target_construction` (or a short
grammatically-plausible fragment of their pattern) as wrong options, shuffled with the
correct answer into `options` A–D. **[ADR-10]** Selection excludes items whose
`target_construction` is identical string to the correct answer's (avoid a trivially
duplicate-looking option) but otherwise is uniform random — no tag/graph similarity (V2, per
SPEC §60). This runs once at question-generation time and is cached into `question.options`
(not recomputed per-serve), matching SPEC §6's "Serve later — не генерировать вопрос в
момент клика".

---

## 8. API surface (MVP)

```
GET  /grammar                      list all 205, paginated/filterable by status
GET  /grammar/{id}                 single item detail (pattern, formation, progress)
POST /review/session               body: {size: 5|10|20} -> selects due items (next_review<=now,
                                    priority: overdue first, then new), triggers shortage-check
                                    generation, returns list of Question (already resolved options)
POST /review/answer                body: {question_id, selected_option, response_time_ms}
                                    -> records QuestionAttempt, runs SRS schedule_next,
                                    returns {is_correct, correct_option, explanation, next_review}
GET  /stats                        due_count, recall_pct (rolling), counts by status
GET  /health                       liveness for hosting platform
```

No auth middleware on MVP (ADR-3). CORS allowlist = the Vercel frontend origin(s) from env.

---

## 9. Task breakdown (dependency-ordered, layer-tagged)

Legend: **P0** = MVP-blocking, **P1** = MVP-nice-to-have, **P2** = V2. Layer tags map 1:1
to dev agents (`DB`→backend-dev, `Backend`→backend-dev, `AI`→ai-engineer or backend-dev,
`Frontend`→frontend-dev, `Infra`→devops, `Test`→qa-tester, `Docs`→tech-writer).

### Phase 1 — DB & seed (must land before backend endpoints)
| # | Layer | Task | Output | Test |
|---|---|---|---|---|
| 1.1 | DB | Write Alembic migration `0001_initial_schema` from §3 DDL | `backend/alembic/versions/0001_*.py` | `alembic upgrade head` on fresh Supabase branch succeeds |
| 1.2 | Backend | SQLAlchemy models mirroring §3 (`app/models/*.py`) | typed ORM models | `mypy`/`pyright` clean |
| 1.3 | Backend | `seed_import.py`: parse Anki JSON per §4 mapping, upsert by `source_note_id`, write import report | populates `grammar` + one `grammar_progress` row per item | run against real `data/seed/*.json` → 205 rows, report shows the 1 known ruby anomaly (ADR-6) and no others |
| 1.4 | Test | Unit tests for `formation_rules` line parser + `target_construction` extraction against edge cases (multi-line, missing `→`, nested ruby) | `tests/test_seed_import.py` | passes on all 205 real rows, no unhandled exceptions |

### Phase 2 — Backend core (parallel-safe once Phase 1 lands)
| # | Layer | Task | Output | Test |
|---|---|---|---|---|
| 2.1 | Backend | `srs.py` per §6 pseudocode | pure functions, no DB coupling | `tests/test_srs.py`: correct-streak progression, error-drops-2-steps, status derivation table |
| 2.2 | Backend | `GET /grammar`, `GET /grammar/{id}` | routers + schemas | integration test against seeded DB |
| 2.3 | Backend | `distractors.py` (uniform random, excludes literal dup) | pure function | unit test: never returns correct answer as distractor, always 3 unique |
| 2.4 | Backend | `POST /review/session` — due-item selection (overdue > new, size 5/10/20), assembles Question payload, calls generation-shortage trigger | router + service | integration test: due-priority ordering, session size respected |
| 2.5 | Backend | `POST /review/answer` — persists `question_attempt`, calls `schedule_next`, updates `grammar_progress` | router + service | integration test: next_review advances correctly on correct/incorrect |
| 2.6 | Backend | `GET /stats` | router | integration test against known seeded state |
| 2.7 | Frontend | `FuriganaText.tsx` — 3 render modes per §5, pure component, unit-testable on static HTML strings | component | snapshot test: Always/Never/By-level on the ADR-6 malformed row too (must not crash) |

### Phase 3 — AI generation pipeline (depends on 2.1–2.4 schema/service shape)
| # | Layer | Task | Output | Test |
|---|---|---|---|---|
| 3.1 | AI | `provider.py` Protocol + config wiring (single-provider-missing-key tolerance per ADR/§9) | interface | unit test: missing inactive provider key never raises |
| 3.2 | AI | `openai_adapter.py` — structured-output call per §7.2/7.3 | adapter | mocked-API unit test against schema |
| 3.3 | AI | `anthropic_adapter.py` — forced tool-use call, same schema | adapter | mocked-API unit test against schema |
| 3.4 | AI | `validate.py` — grammar-fit + dedup-hash per §7.4 | pure functions | unit test: rejects missing target, rejects exact dupe via hash collision |
| 3.5 | AI | `trigger.py` — shortage detection + `BackgroundTasks` wiring, wired into `POST /review/session` (2.4) | service | integration test: shortage triggers background call (mocked provider), non-shortage doesn't |
| 3.6 | Test | End-to-end generation smoke test against **one real provider** (whichever key is available) for a single grammar item, assert a valid `question` row lands | manual/CI-gated (costs tokens) | run once before declaring Phase 3 done |

### Phase 4 — Frontend app (parallel with Phase 3 once API contracts from Phase 2 are stable)
| # | Layer | Task | Output | Test |
|---|---|---|---|---|
| 4.1 | Frontend | `lib/api.ts` typed client for the 6 endpoints (§8) | typed fetch wrappers | type-checks against backend OpenAPI/Pydantic schemas |
| 4.2 | Frontend | Dashboard `app/page.tsx` — due count, status counts, "Start Review" CTA | page | manual QA via `qa` skill |
| 4.3 | Frontend | Review session `app/review/page.tsx` — question → answer → feedback → contrastive explanation → next, session length picker (5/10/20) | page + `QuestionCard.tsx`, `ContrastiveExplanation.tsx` | manual QA, full loop per SPEC §8 acceptance flow |
| 4.4 | Frontend | Stats page `app/stats/page.tsx` | page | manual QA |
| 4.5 | Frontend | PWA manifest + icons + service worker registration (installable, offline app-shell at minimum) | `public/manifest.webmanifest`, icons, SW | Lighthouse PWA check |
| 4.6 | Frontend | Furigana toggle wired into settings (Always/Never/By-level), persisted client-side (localStorage, no backend setting on MVP) | UI control | manual QA |

### Phase 5 — Integration, polish, ship
| # | Layer | Task | Output | Test |
|---|---|---|---|---|
| 5.1 | Test | Full acceptance-flow QA per SPEC §8 (`qa-tester` agent, browser-driven) | bug list or sign-off | pass/fail against the exact flow described |
| 5.2 | Infra | Provision Supabase project + run migrations against it (Supabase MCP available) | live DB | `alembic upgrade head` against Supabase connection string |
| 5.3 | Infra | Deploy backend container (host per ADR-1) + deploy frontend to Vercel (Vercel MCP available), wire env vars (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`DATABASE_URL`/`LLM_PROVIDER`) | live URLs | health check + one real review-session round-trip in prod |
| 5.4 | Docs | `README.md`, `/llms.txt` for the API, `.env.example` completeness check | docs | tech-writer sign-off |

**Parallelization note for the orchestrator:** Phase 2 (2.1-2.6) and Phase 4's static shell
(4.1 typed client stubbed against the *documented* contract, 4.5 PWA scaffolding) can run
concurrently once Phase 1 is done — frontend-dev doesn't need a live backend to build
against a fixed OpenAPI contract, just needs 2.2/2.4/2.5/2.6's request/response shapes
frozen first (already frozen in §8 above). Phase 3 (AI) is independent of Phase 4 entirely
and can run fully in parallel with it.

---

## 10. Config / env vars (`.env.example`)

```
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/postgres
LLM_PROVIDER=anthropic            # anthropic | openai
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GENERATION_SHORTAGE_THRESHOLD=5
GENERATION_BATCH_SIZE=15
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

---

## 11. Open items carried forward (not blocking, tracked for later)

- ADR-6 data anomaly: one malformed `<ruby><rt>` row — import report flags it, owner can
  hand-fix the Anki source later if desired.
- Tag-based distractor/grouping quality is weak on MVP (empty tags) — first V2 target per
  SPEC §9.
- Backend hosting target (ADR-1) is deliberately left open for devops to pick at ship time.

---

## V2 Slice: Grammar Graph & Browse

Status: draft v1 · Basis: `SPEC.md` §4 "Явно вне MVP" (Grammar Graph, browsable curriculum) +
idea doc §10 (relation types) · Author: architect agent · Date: 2026-09-23

MVP shipped Tier 1 (205 items, SRS review loop, QA-verified). This slice adds the two V2
items the owner asked for next: (1) explicit typed relations between grammar items
(`GrammarRelation`), and (2) a first-class browsable Grammar List/Detail UI, distinct from
the review-session-only access pattern of MVP. It does **not** touch SRS, generation
triggers, or the review flow — additive only. ADR numbering continues from ADR-10.

### V2.1 `GrammarRelation` model + migration

**Schema** (scaffolded in `backend/alembic/versions/0002_grammar_relations.py` — migration
file only, model/router/script left for backend-dev per task scope):

```sql
CREATE TYPE grammar_relation_type AS ENUM (
    'similar_meaning', 'similar_form', 'commonly_confused', 'opposite',
    'prerequisite', 'advanced_version', 'related'
);
CREATE TYPE grammar_relation_source AS ENUM ('heuristic', 'llm_classified', 'manual');

CREATE TABLE grammar_relation (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grammar_id          UUID NOT NULL REFERENCES grammar(id) ON DELETE CASCADE,
    related_grammar_id  UUID NOT NULL REFERENCES grammar(id) ON DELETE CASCADE,
    relation_type       grammar_relation_type NOT NULL,
    strength            REAL NOT NULL DEFAULT 1.0,   -- LLM confidence 0..1, or 1.0 for manual/heuristic
    source              grammar_relation_source NOT NULL,
    prompt_version       TEXT,                        -- classification prompt version, audit trail
    note                 TEXT,                        -- optional 1-line LLM justification, shown in UI tooltip
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (grammar_id <> related_grammar_id)
);
CREATE UNIQUE INDEX uq_grammar_relation_edge ON grammar_relation (grammar_id, related_grammar_id, relation_type);
CREATE INDEX ix_grammar_relation_grammar_id ON grammar_relation (grammar_id);
CREATE INDEX ix_grammar_relation_related_grammar_id ON grammar_relation (related_grammar_id);
```

**[ADR-11] Directionality convention.** Idea doc §10 lists 7 relation types without
specifying direction. Decision, per type:
- **Symmetric** (`similar_meaning`, `similar_form`, `commonly_confused`, `opposite`,
  `related`): meaning is identical regardless of which column is which. Stored as **one row
  only**, with the population script (V2.2) always writing the lexicographically-smaller
  `grammar.id` into `grammar_id`. The API expands this into both directions when answering
  "relations of X" (query `WHERE grammar_id = X OR related_grammar_id = X`, and when X is in
  `related_grammar_id`, present the *other* side as "related grammar" — the response shape
  hides which physical column held which id, callers never need to know).
- **Directional** (`prerequisite`, `advanced_version`): `grammar_id` is the "from"/base item,
  `related_grammar_id` is the "to"/target item. `(A, B, prerequisite)` reads "A is a
  prerequisite of B" (learn A first). `(A, B, advanced_version)` reads "B is the advanced
  version of A" (equivalently: A is the simpler/base form of B). These two directional types
  are usually a matched pair for the same underlying relationship (if A→B is `prerequisite`,
  the population script may also emit A→B `advanced_version` is *not* required — pick
  whichever single type best fits per the classification prompt in V2.2; don't force both).
  The API surface for a directional edge includes an explicit `"direction": "outgoing" |
  "incoming"` field relative to the grammar item being viewed, so the frontend can render
  "Prerequisite for this" vs. "Requires this first" correctly without the client re-deriving
  direction semantics.

No `owner_id`/user scoping needed (ADR-3 still holds — personal tool).

### V2.2 Relation population strategy — heuristic candidates + one LLM classification pass

**Decision: option (b), heuristic candidate generation → single batched LLM classification
pass.** All-pairs O(205²) ≈ 21,000 pairs run through an LLM is wasteful (most pairs have no
meaningful relation) and expensive even at cheap per-call pricing; it also produces a huge
majority of "none" responses the classifier has to actively reject, which is where LLM
classification quality degrades. Cheap heuristics narrow the field to the pairs actually
worth asking about, and the existing dual-provider abstraction (`app/services/generation/`)
is reused for the single classification pass rather than building a second one from scratch.

**Step 1 — heuristic candidate generation (`backend/app/scripts/generate_relations.py`,
pure Python, no LLM calls, runs in milliseconds over 205 rows):**

For every unordered pair `(A, B)` of grammar items, compute a candidate score from cheap
signals available directly on the `grammar` row (no new data needed):
1. **Shared tail/function-word match** on `expression_clean` / `target_construction` — many
   N3 confusable sets share a suffix or particle cluster (e.g. `わけだ`/`わけではない`/`わけがない`/
   `わけにはいかない` per idea doc §10's own example). Strip the common grammatical root
   (`わけ`, `ば`, `たら`, `のに`, `ながら`, etc. — a small hardcoded list of ~30 N3 function-word
   stems is enough, extracted once from scanning the 205 `target_construction` values) and
   flag pairs sharing a stem — strong signal for `similar_form`/`commonly_confused`.
2. **Keyword overlap in `meaning_ru`** — tokenize (lowercase, strip punctuation, drop Russian
   stopwords), Jaccard similarity over token sets. High overlap → `similar_meaning` candidate.
   Antonym-flagging (`opposite`) is a fixed keyword-pair list (не/не-/наоборот cues,
   "хотя"/"поэтому" opposite-logic markers) checked against both items' `pattern_text` —
   weak signal, kept as a *candidate* trigger only, real classification is the LLM's job.
3. **Shared kanji in `expression_clean`** (excluding function-word-only items with no kanji)
   — set overlap on individual kanji characters, weighted by rarity (a shared common kanji
   like 見 is weak evidence; a shared rare kanji is stronger). Cheap proxy for topical/lexical
   relation.
4. Combine 1-3 into a single score; take **top 6 candidate partners per item** (symmetric
   dedup: pair `(A,B)` kept once). This caps the candidate set at ≤ `205 × 6 / 2 ≈ 615` pairs
   in the worst case, typically fewer once dedup and score thresholds apply — roughly
   **30x fewer LLM-evaluated pairs than all-pairs**, while heuristic step 1 (the strongest
   signal, since it's this deck's actual construction-family clusters) directly targets the
   `commonly_confused`/`similar_form` pairs the review loop's distractor quality (SPEC §9's
   flagged risk) most needs.
5. **Sparse-item fallback**: items with < 3 candidates after step 4 (isolated grammar points
   with no obvious lexical/semantic neighbor) are left sparse — acceptable for a personal
   tool; noted as an open item (§V2.5) rather than solved with embeddings on this pass.

**Step 2 — single batched LLM classification pass, reusing the provider abstraction:**

Extend `LLMProvider` (protocol in `app/services/generation/provider.py`) with one additional
method, implemented by both `openai_adapter.py` and `anthropic_adapter.py` alongside the
existing `generate_sentences`:

```python
@dataclass(frozen=True, slots=True)
class RelationCandidate:
    grammar_a_id: str
    grammar_a_text: str      # target_construction + short pattern_text summary
    grammar_a_meaning: str
    grammar_b_id: str
    grammar_b_text: str
    grammar_b_meaning: str

@dataclass(frozen=True, slots=True)
class RelationClassification:
    grammar_a_id: str
    grammar_b_id: str
    relation_type: str | None   # one of the 7 enum values, or None = "no meaningful relation"
    direction: str | None       # "a_to_b" | "b_to_a", only meaningful for prerequisite/advanced_version
    strength: float             # 0..1 confidence
    note: str                   # 1-sentence justification, stored verbatim in grammar_relation.note

class LLMProvider(Protocol):
    async def generate_sentences(self, prompt: GenerationPrompt) -> list[RawGeneratedSentence]: ...
    async def classify_relations(self, candidates: list[RelationCandidate]) -> list[RelationClassification]: ...
```

Same structured-output pattern as §7.2 (OpenAI `json_schema` / Anthropic forced tool-use),
batched **~40 candidate pairs per call** (stays well inside both providers' context/output
limits and keeps a single malformed response from invalidating the whole run) — for ~600
candidates that's **~15 LLM calls total** for the entire relation graph, a one-time cost, not
a per-review-session cost. Prompt gives both items' `target_construction`, `pattern_text`,
`meaning_ru`, and formation info, asks the model to pick the best-fitting relation type (or
"none"), a direction when directional, and a confidence + one-line reasoning. `None`
responses are simply discarded (no row written).

**Step 3 — persist**: upsert into `grammar_relation` with `source='llm_classified'`,
`prompt_version` set (same pattern as `Question.generation_prompt_version`), applying the
ADR-11 canonicalization (symmetric types: smaller id → `grammar_id`; directional types: use
the model's stated direction to pick which id is `grammar_id`). Re-running the script is
idempotent via `ON CONFLICT (grammar_id, related_grammar_id, relation_type) DO UPDATE` (a
rerun with better heuristics/prompt refreshes `strength`/`note` without duplicating edges).

**[ADR-12] Where this runs.** One-time/occasional manual script
(`uv run python -m app.scripts.generate_relations`), **not** a background job and **not**
wired into any request path — unlike `trigger.py`'s per-session generation, relations don't
need to exist before the owner's next click, and re-running it costs real API tokens the
owner should trigger deliberately. Owner runs it once after this slice ships, and can re-run
later if the deck grows or classification quality needs a prompt-version bump. Script prints
a summary report (`generate_relations_report.json`: candidate count, classified count, count
by relation_type, count of "none" responses, list of items still with zero relations after
the pass) mirroring the `seed_import.py` report pattern already established.

### V2.3 API surface (extends, does not redesign, the existing `grammar.py` router)

Current `GET /grammar` returns the full unpaginated list (fine at 205 rows, but §4's "first-class
browsable" ask plus this section's search/filter needs a small, backward-compatible extension.
`GET /grammar/{id}` currently returns bare `GrammarOut` (no progress, no relations) — extend it.

```
GET /grammar?q=&status=&tag=&limit=&offset=
    q       - optional, case-insensitive substring match across expression_clean,
              reading, meaning_ru, pattern_text (Postgres ILIKE across the four columns
              OR'd together — no need for full-text search infra at 205 rows)
    status  - optional, filter by grammar_progress.status (new|learning|review|mastered)
    tag     - optional, filter by tags array containment (kept for forward-compat; currently
              a no-op filter since all tags are empty per ADR-4 — do not remove, tags may get
              populated later)
    limit, offset - optional pagination, default limit=205 offset=0 (i.e. "return everything"
              stays the default behavior, existing frontend callers are unaffected)
    -> {"items": [GrammarWithProgressOut, ...], "total": <int>}   # wrapper is the one
       breaking change vs MVP's bare list[GrammarOut] — bump frontend's lib/api.ts accordingly

GET /grammar/{id}
    -> GrammarDetailOut = GrammarWithProgressOut + {
         "relations": [
           {
             "relation_type": "commonly_confused",
             "direction": "symmetric" | "outgoing" | "incoming",
             "strength": 0.86,
             "note": "both mean 'while X, Y' but わけではない negates the outcome, not the cause",
             "related_grammar": {"id": "...", "expression_clean": "...", "reading": "...",
                                  "meaning_ru": "...", "target_construction": "..."}
           }, ...
         ]
       }
    Relations embedded directly (no separate round-trip) since counts per item are small
    (heuristic caps candidates at 6, most items end up with 0-6 relation rows).

GET /grammar/{id}/relations
    -> same array as the "relations" field above, standalone endpoint for cases that don't
       need the full grammar payload (e.g. a relations-only refresh after editing).

GET /grammar/relations
    -> ALL edges in one call: [{"grammar_id", "related_grammar_id", "relation_type",
       "direction", "strength"}, ...]. Purpose-built for the graph view (V2.4) so it can
       render the whole ~205-node graph from two calls total (this + GET /grammar for node
       labels) instead of N+1 per-node relation fetches.
```

Schemas: extend `backend/app/schemas/grammar.py` with `GrammarRelationOut`,
`GrammarDetailOut`, `GrammarListOut` (the `{items, total}` wrapper) alongside the existing
`GrammarOut`/`GrammarWithProgressOut` — additive, don't rename or remove the current models
(other MVP endpoints/tests reference them).

### V2.4 Frontend — Grammar List, Detail, and Graph views

**No new dependencies.** `frontend/package.json` currently has zero UI/graph/state libs
beyond Next.js + React + Tailwind — per the task's own steer, this stays true. All three new
views below are built with what's already installed.

**`app/grammar/page.tsx` (list/browse):**
- Fetch `GET /grammar` once on mount (205 rows is trivial payload size, ~50-100KB of JSON at
  most); search/filter/sort happen **client-side** over the already-fetched array — no need
  to round-trip to the backend's `?q=` param for a personal single-user 205-item list (the
  backend param exists per V2.3 for completeness/future-proofing, e.g. if the deck grows to
  N5-N1 combined per SPEC's V2 list, but the MVP-era frontend doesn't need it yet).
- Controls: text search input (matches `expression_clean`/`reading`/`meaning_ru`), status
  filter chips (new/learning/review/mastered, reusing `GrammarProgress.status` already
  returned), a link/toggle to the graph view.
- List rendered as a simple card/row list (reuse Tailwind patterns from the existing
  dashboard), each row links to `/grammar/[id]`.

**`app/grammar/[id]/page.tsx` (detail):**
Structured per idea doc §35's intent (full info block, not just the review-session sentence
fragment): meaning, formation table (reuse `formation_rules` jsonb, same data
`FuriganaText.tsx` already knows how to render from MVP), the original Anki example sentence
(`expression_html`), usage/nuance text (`pattern_text` — already carries both the rule and
nuance per SPEC §3's field description, no new field needed), and a **"Compare with…"**
block driven by `relations`: grouped by `relation_type` (e.g. a "Commonly confused with"
section, a "Similar meaning" section, a "Prerequisite / builds on" section using
`direction`), each entry linking to that related item's own detail page. This is the payoff
of V2.1/V2.2 — distractor quality and study-flow are no longer blind.

**`app/grammar/graph/page.tsx` (graph visualization):**
Fetch `GET /grammar` (node labels) + `GET /grammar/relations` (edges) once, render with a
**hand-rolled force-directed layout, computed once client-side, no d3 or react-force-graph
dependency**:
- Layout: simple iterative repulsion/spring relaxation (Fruchterman-Reingold-style) run for
  ~150-300 iterations in a `useEffect` on load — O(n²) repulsion over 205 nodes is a few
  hundred thousand operations, trivially fast in a single JS tick, no per-frame animation
  loop needed (compute layout once, then it's a static positioned graph you pan/zoom, not a
  live physics sim). ~20-30 lines of vector math, no library.
- Render: `<canvas>` (not SVG) for the ~205 nodes / up to ~600 edges — canvas draw calls at
  that count are cheap and avoid SVG DOM-node overhead; label text drawn only for
  hovered/selected node plus optionally always-on for high-degree "hub" nodes (commonly the
  most useful ones to see labeled).
- Interaction: hover highlights a node's direct edges + dims the rest; click navigates to
  `/grammar/[id]`; a relation-type legend with toggleable visibility per type (color-coded:
  e.g. red=commonly_confused, blue=similar_meaning, gray=related, arrow-style edges for the
  two directional types vs. plain lines for symmetric ones); basic pan (drag) and zoom
  (wheel) on the canvas transform.
- **[ADR-13]** If this hand-rolled approach turns out visually janky in practice (uneven
  clustering, overlap) frontend-dev's fallback is `d3-force` alone (not `d3` in full, not
  `react-force-graph` which pulls in three.js/WebGL for a 205-node 2D graph — massive
  overkill) — a single, narrowly-scoped, well-maintained physics-only package. Try the
  zero-dependency version first; this is a nice-to-have visualization for a personal tool,
  not worth over-engineering per the task's own steer.

### V2.5 Task breakdown (dependency-ordered, layer-tagged)

Continues the MVP task-numbering convention (§9); phases here are additive, run after MVP
Phase 5 shipped.

| # | Layer | Task | Output | Test |
|---|---|---|---|---|
| V2.1 | DB | Migration `0002_grammar_relations` — **scaffolded already**, verify against a live DB | `backend/alembic/versions/0002_grammar_relations.py` | `alembic upgrade head` succeeds on Supabase branch |
| V2.2 | Backend | `app/models/grammar_relation.py` SQLAlchemy model mirroring the DDL, add relationship on `Grammar` (both `grammar_id`/`related_grammar_id` sides — two `relationship()`s or a helper property that merges them per ADR-11) | model | `mypy` clean, model round-trips a row in a unit test |
| V2.3 | AI | Extend `LLMProvider` protocol + both adapters with `classify_relations` (§V2.2 step 2) | `provider.py`, `openai_adapter.py`, `anthropic_adapter.py` changes | mocked-API unit test against the `RelationClassification` schema |
| V2.4 | AI | `backend/app/scripts/generate_relations.py` — heuristic candidate generation (pure Python, §V2.2 step 1) + batched classification calls + upsert + report | script + `generate_relations_report.json` | unit tests for the heuristic scorer against known N3 confusable sets (e.g. the わけ family from idea doc §10) score high; manual one-time run against real 205-row DB before declaring this task done (costs tokens — owner-gated like MVP Phase 3.6) |
| V2.5 | Backend | Extend `grammar.py` router + `schemas/grammar.py`: `?q=/status=/tag=/limit=/offset=` on list, `GrammarDetailOut` with embedded relations on detail, new `GET /grammar/{id}/relations` and `GET /grammar/relations` | router + schema changes | integration tests: search matches expected rows, detail embeds correct relation count/direction, `/grammar/relations` returns full edge set |
| V2.6 | Frontend | `lib/api.ts` additions for the 2 new/changed endpoints; update any MVP caller of bare `GET /grammar` for the new `{items, total}` wrapper | typed client | type-checks against updated backend schema |
| V2.7 | Frontend | `app/grammar/page.tsx` list/search/filter | page | manual QA: search narrows correctly, status chips filter, 205 items all reachable |
| V2.8 | Frontend | `app/grammar/[id]/page.tsx` detail + "Compare with…" relations block | page | manual QA against a few known relation-rich items post V2.4 run |
| V2.9 | Frontend | `app/grammar/graph/page.tsx` hand-rolled force-directed canvas view | page + `components/GrammarGraph.tsx` | manual QA: layout is legible (no total-overlap collapse), hover/click/pan/zoom work, relation-type legend toggles visibility |
| V2.10 | Test | QA pass across V2.5-V2.9 end to end (`qa-tester`) | bug list or sign-off | browse → detail → compare-with-link → graph → click-back-to-detail loop works |
| V2.11 | Docs | Update `/llms.txt` + README for the 4 new/changed endpoints | docs | tech-writer sign-off |

**Parallelization:** V2.2 (DB model) blocks V2.3/V2.4 (need the table to write into) and
V2.5 (need the model to query). V2.3+V2.4 (AI) and V2.5 (Backend API) can run in parallel
once V2.2 lands, since V2.5's new endpoints can be built/tested against manually-inserted
rows before V2.4's real classification run completes. V2.6-V2.9 (Frontend) can start against
the frozen contract in §V2.3 as soon as V2.5 is merged, independent of whether V2.4's actual
LLM run has happened yet (empty relations arrays render fine, just an empty "Compare with…"
section) — mirrors the MVP task plan's "frontend doesn't need a live backend, just a frozen
contract" note.

### V2.6 Open items carried forward

- Sparse-relation items (§V2.2 step 5, heuristic candidates < 3) may end up with zero edges
  after classification too — acceptable for personal tool, revisit if it turns out to be a
  large fraction of the 205 after the first real run (the `generate_relations_report.json`
  makes this visible).
- `tag`-based filtering (§V2.3) is a no-op until tags are populated (ADR-4 still holds) —
  kept in the API for forward-compat, not for this slice to solve.
- Embedding-based candidate generation (mentioned as a fallback in SPEC §6/§9's dedup
  discussion) is explicitly not used here either (ADR-9's reasoning extends to this slice) —
  revisit only if the heuristic step's candidate quality proves too weak in practice.

---

## V3 Slice: Adaptive Practice & Vocabulary

Status: draft v1 · Basis: idea doc §15/§21-23/§28/§36/§37, SPEC.md's explicitly-deferred V2
list · Author: architect agent · Date: 2026-09-23

MVP + the Grammar Graph/Browse V2 slice are both shipped and QA-verified. This slice covers
everything left in SPEC.md's V2 tier the owner asked for in one pass: Confusion Practice,
Weak Points, adaptive furigana via a new `Vocabulary`/`UserVocabulary` pair, and a modest
confusion-bias wire-through into the existing distractor/generation pipeline. **Additive
only** — no MVP/V2 table, endpoint, or algorithm is redesigned; `review.py`'s existing
`select_due_progress`/`serve_question_for_grammar`/`apply_answer` and `distractors.py`'s
`pick_distractors` are extended in place, not forked. ADR numbering continues from ADR-13.

Scope calls made up front, per the task's own "simplify aggressively" steer:
- No morphological tokenizer. Word-boundary detection is sidestepped entirely (not
  approximated) by reusing the sentence markup's existing `<ruby>base<rt>reading</rt></ruby>`
  spans, which are already segmented at word/compound granularity by whoever authored the
  Anki deck and by the AI generation prompt (§7.3, which explicitly asks for the same ruby
  convention). See **[ADR-15]** below — this is the single design choice that makes the rest
  of this slice tractable at personal-tool effort level.
- No new stats dashboard, no vocabulary browse UI, no per-word quiz mode. Vocabulary tracking
  is purely an SRS-adjacent signal (drives furigana hiding), not a feature surface of its own.
- No session-composition config UI. Mix ratios/thresholds below are hardcoded constants in
  `config.py`, changeable by editing `.env` — not worth a settings screen for a single user.

### V3.1 Schema: `Vocabulary` + `UserVocabulary`

**Migration scaffolded** at `backend/alembic/versions/0003_vocabulary.py` (mirrors 0002's
structure) — model/router/service left for backend-dev.

```sql
CREATE TYPE vocabulary_entry_type AS ENUM ('word', 'kanji');

CREATE TABLE vocabulary (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    surface_form              TEXT NOT NULL,        -- exact string matched against <ruby> base spans
    entry_type                vocabulary_entry_type NOT NULL DEFAULT 'word',
    reading                   TEXT NOT NULL,
    meaning_ru                TEXT NOT NULL,
    example_sentence_jp       TEXT,
    example_sentence_reading  TEXT,
    example_sentence_ru       TEXT,
    jlpt_level                VARCHAR(8) NOT NULL DEFAULT 'N3',
    source_tag                TEXT,                  -- CSV category (words) or on/kun readings (kanji)
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_vocabulary_surface_form ON vocabulary (surface_form);
CREATE UNIQUE INDEX uq_vocabulary_surface_entry_type ON vocabulary (surface_form, entry_type);

CREATE TABLE user_vocabulary (
    vocabulary_id       UUID PRIMARY KEY REFERENCES vocabulary(id) ON DELETE CASCADE,
    correct_exposures   INTEGER NOT NULL DEFAULT 0,   -- lifetime counter, for stats only
    incorrect_exposures INTEGER NOT NULL DEFAULT 0,   -- lifetime counter, for stats only
    correct_streak      INTEGER NOT NULL DEFAULT 0,   -- drives known_since, reset on any miss
    known_since         TIMESTAMPTZ,                  -- non-null => furigana hidden (adaptive mode)
    last_exposed_at     TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

No `owner_id` (ADR-3 still holds). A row is created lazily in `user_vocabulary` the first
time a word is matched in a served sentence (not pre-populated for all ~2,600 vocabulary
rows — most will never be exposed at N3-only review volume, no reason to pre-seed dead rows).

**[ADR-14] Seed source is a repo-local JSON snapshot, not a live read of the external CSV
directory.** `E:\Main\Main\Папки\Japanese\Анки\{кандзи н3,слова н3}\*.csv` is outside this
repo (a separate personal working directory, explicitly read-only reference per the task).
Mirrors the exact precedent SPEC §3 already set for `Grammar` (Anki export copied into
`data/seed/n3_grammar_anki_export.json` rather than read live from the `.apkg`): the seed
script reads the external CSVs **once**, writes `data/seed/vocabulary_n3.json` into the repo,
and the actual DB-populating script reads that snapshot. This means the backend never depends
on the external drive/folder being present at deploy time, in CI, or on any machine but the
owner's dev box where the one-off conversion is run.

**[ADR-15] Exact-match against `<ruby>` base spans, not substring/tokenization.** Extracting
word boundaries from unsegmented Japanese text is a known-hard problem the task explicitly
says to sidestep. The insight that avoids it: every sentence this app ever serves
(`sentence_full_html`, both seed and AI-generated per the §7.3 prompt contract) already
carries `<ruby>base<rt>reading</rt></ruby>` spans, and `base` is already segmented at
word/compound granularity — because that's the only granularity furigana annotation makes
sense at. So vocabulary matching is: parse every `<ruby>` pair out of `sentence_full_html`
(reusing the existing `_RUBY_PAIR_RE` regex already defined in
`backend/app/services/furigana.py` and mirrored in `frontend/src/components/FuriganaText.tsx`
— exported/shared rather than re-implemented a third time, see V3.4), strip any inner tags
from `base`, and look up that exact string against `vocabulary.surface_form`. No substring
scan over the full sentence text against ~2,600 candidate strings, no ambiguity about
whether a matched kanji is part of a larger word — the markup already answered that
question. This only works because kanji-only vocabulary rows (`entry_type='kanji'`) are
matched **exactly** too: a single-kanji `<ruby>` base like `<ruby>実<rt>み</rt></ruby>` will
exact-match a kanji-deck row, but will never spuriously match against a *different* compound
like `現実` (whose ruby base is the two-character string `現実`, not `実` alone) — exact-match
naturally respects the segmentation the source markup already committed to.

Sentences whose target construction has no kanji, or with a stray un-ruby'd kanji, simply
contribute no vocabulary signal for that word — acceptable gap, not a data-quality bug to
chase (mirrors ADR-6/ADR-6b's general stance on this deck's markup quality).

**[ADR-16] "Known" rule.** Per idea doc §22 verbatim intent ("known after N correct
exposures"): `known_since` is set the first time `correct_streak >= KNOWN_STREAK_THRESHOLD`
(config, default `5`). Any single incorrect exposure resets `correct_streak` to 0 **and**
clears `known_since` back to `NULL` if it was set — a word can un-become "known" if the owner
starts missing it again, mirroring `grammar_progress`'s own lapse philosophy (ADR-8: partial
regression on error, not amnesia, but also not silently ignoring a real miss). Streak-based
rather than raw-total-based specifically so a word that was correct 5 times long ago but has
been missed every time since doesn't stay marked "known" forever.

### V3.2 Vocabulary seeding — CSV structure (confirmed by reading actual files)

Both CSV families are **headerless**, comma-separated, UTF-8 with a BOM on the first field of
row 1. Confirmed columns (no column ever contains an embedded comma in the sampled data —
plain `csv.reader` with default dialect is sufficient, no quoting edge cases hit):

- **`слова н3/*.csv`** (22 files, 2,312 data rows total) — one word per row:
  `surface_form, reading, meaning_ru, example_sentence_jp, example_sentence_reading,
  example_sentence_ru, category_tag` (e.g. `教育,きょういく,образование,日本の教育制度について...,
  にっぽんの...,Изучаю систему...,N3::Education`). → `entry_type='word'`, `source_tag` =
  column 7 verbatim.
- **`кандзи н3/*.csv`** (15 files, 373 data rows total) — one kanji per row: `kanji_char,
  primary_kun_reading, on_readings, all_kun_readings, meaning_ru, compound_examples,
  example_sentence_jp, example_sentence_ru` (e.g. `合,あう,ゴウ・ガッ,あう・あわす・あわせる,
  соединение/подходящий,合う（あう）—...,この色は君に合います。,Этот цвет тебе подходит.`).
  → `entry_type='kanji'`, `surface_form` = column 1, `reading` = column 2 (the reading that
  actually appears standalone in running text; on/kun full lists packed into `source_tag` as
  `f"on={col3} kun={col4}"` for audit purposes only, not used for matching).

`seed_vocabulary.py` (`backend/app/scripts/seed_vocabulary.py`, one-off/re-runnable like
`generate_relations.py`, **not** wired into any request path):
1. Read both directories (path from `settings.vocabulary_csv_source_dir`, default pointing at
   the path above — overridable since it's a personal path on the owner's machine, not
   portable, mirrors how `.env` already isn't committed).
2. Parse rows per the column mapping above; dedupe within each family by `surface_form`
   (a handful of words plausibly repeat across category files — first occurrence wins, note
   the collision count in the report rather than silently dropping data).
3. Write `data/seed/vocabulary_n3.json` (both families in one file, tagged by `entry_type`) —
   the repo-committed snapshot per ADR-14.
4. Upsert into `vocabulary` on `(surface_form, entry_type)` conflict — updates
   `reading`/`meaning_ru`/examples/`source_tag`, never touches `user_vocabulary` (re-running
   this script must never reset the owner's retention progress).
5. Print/write `seed_vocabulary_report.json` (rows read per family, rows written, dedup
   collisions) — same reporting convention as `seed_import.py`/`generate_relations.py`.

Expected result: ~2,300-2,600 `vocabulary` rows total (word + kanji, minus dedup collisions).

### V3.3 Confusion Practice & Weak Points review modes

**API change**: `SessionRequest` (`backend/app/schemas/review.py`) gets one new field:

```python
class SessionRequest(BaseModel):
    size: Literal[5, 10, 20] = 10
    mode: Literal["due", "confusion", "weak_points"] = "due"
```

`POST /review/session` dispatches on `mode`, all three branches reusing the existing
`serve_question_for_grammar` / shortage-triggered generation / response assembly loop in
`routers/review.py` untouched — only the **selection** step (`select_due_progress` today)
changes per mode. Three new pure-selection functions added to `services/review.py`:

**`select_confusion_progress(db, size)`** — Confusion Practice (idea doc §15). Queries
`grammar_relation WHERE relation_type IN ('commonly_confused', 'similar_form')` (both types,
per the task's own steer: "design this mode to work with whatever `commonly_confused`/
`similar_form` edges exist now" — the no-API-key heuristic fallback in `generate_relations.py`
*never* emits `commonly_confused`, only `similar_form`/`similar_meaning`/`related`, so
restricting to `commonly_confused` alone would make this mode return nothing at all on the
owner's current DB state). Flattens both edge endpoints into a `grammar_id -> max(strength)`
map, orders descending, takes the top `size` distinct grammar items, loads their
`GrammarProgress` rows (every `Grammar` row has one, ADR-5). **Ignores due-ness entirely** —
per the task spec, this mode is "10-20 questions drawn only from grammar items connected by
confusion edges," not a due-review queue. If fewer than `size` grammar items participate in
any qualifying edge (possible before the owner ever runs `generate_relations.py`, or if it's
never run with a real LLM key), the session is simply shorter than requested — surfaced to
the frontend as `SessionResponse.questions` having fewer items than `size` asked for (already
a valid, handled state today: MVP's own due-selection can already under-fill a session when
few items are due). No error, no fake padding.

**`select_weak_progress(db, size, exclude_ids=frozenset())`** — Weak Points (idea doc §28/§37,
SPEC §4 note). Queries `grammar_progress WHERE repetitions > 0` (excludes never-attempted
`NEW` items — their `application_score`/`discrimination_score` are default `0.0`, which would
otherwise make every unseen item look maximally "weak" and dominate the list; weakness must be
*demonstrated*, not assumed), `ORDER BY (application_score + discrimination_score) ASC,
next_review ASC LIMIT size`, excluding any id already in `exclude_ids` (used by the due-mode
mix-in below to avoid duplicate items in one session).

**Default `due` mode gets a weak-point mix-in**, not just a pure switch — per the task's
explicit ask ("weight session composition... even outside 'due' review"):

```python
def select_due_progress_mixed(db, size, now, weak_ratio=settings.weak_point_mix_ratio):
    weak_slots = round(size * weak_ratio) if size >= 5 else 0   # e.g. size=10 -> 2 slots
    due_items = select_due_progress(db, size - weak_slots, now)
    weak_items = select_weak_progress(db, weak_slots, exclude_ids={p.grammar_id for p in due_items})
    combined = due_items + weak_items
    if len(combined) < size:   # not enough weak-eligible items existed — top up from due
        combined += [p for p in select_due_progress(db, size, now)
                     if p.grammar_id not in {x.grammar_id for x in combined}][: size - len(combined)]
    return combined[:size]
```

**[ADR-17] `weak_point_mix_ratio` default `0.2`, hardcoded config, not exposed in the UI.**
20% of a default 10-question session = 2 weak-point questions mixed into ordinary due review,
without displacing the SRS due-queue's own priority ordering for the rest. `size < 5`
(i.e. only the `5`-question option) skips the mix-in entirely — reserving even one slot out
of 5 would over-weight it relative to the ratio's intent. This is the same "modest, wire
existing signals in, no new subsystem" instruction applied to session composition as it was
applied to generation/distractors below.

Router change in `routers/review.py`'s `start_session`: replace the current unconditional
`select_due_progress(db, request.size, now)` call with a 3-way dispatch on `request.mode`
(`due` → `select_due_progress_mixed`, `confusion` → `select_confusion_progress`,
`weak_points` → `select_weak_progress`); everything downstream is unchanged.

### V3.4 Adaptive furigana

Furigana rendering is **entirely client-side today** (confirmed: `services/furigana.py`
exists but is called by no router — `FuriganaText.tsx`/`useFuriganaMode.ts` do the actual
work, over the raw `sentence_full_html` the backend already sends, per a local
`localStorage`-persisted mode toggle). Adaptive mode extends that existing pure-function
pattern rather than moving rendering server-side.

**New `FuriganaMode` value: `"adaptive"`** (both
`backend/app/services/furigana.py:FuriganaMode` and `frontend/src/lib/types.ts`'s mirrored
type go from 3 to 4 literal values). Semantics: start from the existing `"by_level"` baseline
(target-construction furigana hidden), **then additionally strip `<rt>` for any `<ruby>` span
whose base text exact-matches a currently-known word** (ADR-15/16's mechanism, applied at
render time instead of exposure-recording time):

```python
# furigana.py
@beartype
def strip_known_words(html: str, known_surface_forms: frozenset[str]) -> str:
    """Additionally strip <rt> for <ruby> spans whose base is in known_surface_forms.
    Applied on top of by_level baseline for mode='adaptive'. Exact-match only (ADR-15)."""
    def _drop_if_known(match: re.Match[str]) -> str:
        base = _STRIP_TAGS_RE.sub("", match.group(1))
        return match.group(1) if base in known_surface_forms else match.group(0)
    return _RUBY_PAIR_RE.sub(_drop_if_known, html)

# render_furigana() gains a `known_surface_forms: frozenset[str] = frozenset()` parameter;
# mode == "adaptive" -> strip_known_words(strip_furigana_inside_bold(sanitized), known_surface_forms)
```

`frontend/src/components/FuriganaText.tsx`'s `renderFuriganaHtml` gets the mirrored TS
implementation (same file already documents that it deliberately mirrors the Python — this
slice keeps that pairing, adds a 4th case + a `knownSurfaceForms: Set<string>` parameter
threaded through `FuriganaTextProps`).

**Where the known set comes from**: `SessionResponse` (`schemas/review.py`) gains one field,
computed once per session start (not per-question — the known set is a global snapshot, not
per-item):

```python
class SessionResponse(BaseModel):
    questions: list[QuestionOut]
    known_words: list[str]   # surface_form of every vocabulary row with known_since IS NOT NULL
```

`services/vocabulary.py` (new) provides `known_surface_forms(db) -> frozenset[str]` — a single
`SELECT surface_form FROM vocabulary JOIN user_vocabulary ON ... WHERE known_since IS NOT
NULL`, expected to stay in the low hundreds of rows at most even at full N3 mastery, trivial
payload size added to the session response. `routers/review.py`'s `start_session` calls it
once and includes it in `SessionResponse`. The frontend threads `known_words` (as a `Set`)
from the session response down to every `FuriganaText` render for that session — **[ADR-18]**
deliberately not re-fetched mid-session on every answer: knowledge state changes slowly
(streak-based, ADR-16) and a session-stale known-set is a fine trade for avoiding an extra
round-trip per answer, refreshed naturally at the next session start.

**Exposure recording** happens in `POST /review/answer` (`routers/review.py`'s
`submit_answer`), alongside the existing `QuestionAttempt` write and `apply_answer` SRS call:

```python
# services/vocabulary.py
@beartype
def extract_ruby_bases(html: str) -> list[str]: ...   # reuses furigana._RUBY_PAIR_RE, strips inner tags

@beartype
def record_exposures(db: Session, sentence_full_html: str, is_correct: bool, now: datetime) -> None:
    bases = set(extract_ruby_bases(sentence_full_html))
    if not bases:
        return
    vocab_rows = db.scalars(select(Vocabulary).where(Vocabulary.surface_form.in_(bases))).all()
    for vocab in vocab_rows:
        uv = db.get(UserVocabulary, vocab.id) or UserVocabulary(vocabulary_id=vocab.id)
        db.add(uv)
        if is_correct:
            uv.correct_exposures += 1
            uv.correct_streak += 1
            if uv.correct_streak >= settings.known_streak_threshold and uv.known_since is None:
                uv.known_since = now
        else:
            uv.incorrect_exposures += 1
            uv.correct_streak = 0
            uv.known_since = None   # relapse — see ADR-16
        uv.last_exposed_at = now
```

Called once per answer with `question.sentence_full_html` and the already-computed
`is_correct`. **[ADR-19] Whole-sentence correctness is credited to every word in that
sentence, not per-word comprehension** — this is the explicit approximation the task calls
for ("this is an approximation, not a dedicated vocab quiz"): getting the grammar blank right
doesn't prove the learner understood every content word, and getting it wrong doesn't mean
every word was unknown. Accepted as pragmatically good-enough signal for a personal tool;
revisit only if it visibly misbehaves in practice (e.g. words getting marked "known" too
easily because most answers skew correct at high recall_pct).

### V3.5 Confusion-biased distractors + generation prompt

Two minimal, additive changes — no new subsystem, per the task's own steer.

**Distractor selection** (`services/distractors.py`): `pick_distractors` gains an optional
`preferred: list[str] | None = None` parameter, tried before the uniform-random pool:

```python
@beartype
def pick_distractors(correct_grammar_id, correct_answer_text, candidates, count=3,
                      rng=None, preferred=None) -> list[str]:
    rng = rng or random.Random()
    preferred_pool = [t for t in (preferred or []) if t.strip() != correct_answer_text.strip()]
    rng.shuffle(preferred_pool)
    chosen = preferred_pool[:count]
    remaining = count - len(chosen)
    if remaining > 0:
        pool = [text for gid, text in candidates
                if gid != correct_grammar_id and text.strip() != correct_answer_text.strip()
                and text not in chosen]
        if len(pool) < remaining:
            raise ValueError(...)
        chosen += rng.sample(pool, remaining)
    return chosen
```

`services/generation/trigger.py`'s `_build_options` passes `preferred` = the
`target_construction` of every grammar item connected to this one via a
`commonly_confused`/`similar_form` `GrammarRelation` edge (a new
`_fetch_confused_texts(db, grammar_id) -> list[str]` helper, one indexed query on
`grammar_relation`, same pattern as `_fetch_distractor_candidates`). Net effect: once
`generate_relations.py` has populated real confusion edges for an item, freshly-generated
questions for it get distractors drawn from its *actual* confusable partners first — directly
improving discrimination quality (SPEC §9's flagged MVP risk) without touching validation,
storage, or serving logic. Falls back to today's uniform-random behavior automatically when
no edges exist yet (empty `preferred` list) — zero behavior change for any grammar item
without confusion data.

**Generation prompt bias** (`services/generation/prompts.py` + `trigger.py`): when a grammar
item has ≥1 `commonly_confused`/`similar_form` partner, `build_prompt` receives an additional
optional `confusable_with: list[dict[str, str]]` (each partner's `target_construction` +
`meaning_ru`, top 2 by relation `strength`) and appends one line to the existing prompt
template (§7.3): *"This construction is sometimes confused with: {list}. Where natural, favor
sentence contexts that would also work as a contrastive example against these."* This both
(a) improves the `explanation_ru` the LLM already returns per sentence (more likely to
reference the real confusable partner instead of a generic contrast), and (b) is the "confusion
edge gets more questions" intent from idea doc §36 realized as a quality nudge on generation
that already happens, rather than a separate quantity-bias mechanism — **[ADR-20]** a true
"generate more for confusion-linked items" would mean a per-item shortage threshold override;
rejected as unnecessary complexity for a personal tool where `GENERATION_BATCH_SIZE=15` per
trigger already comfortably covers `size<=20` Confusion Practice sessions without a boosted
threshold. If real usage shows confusion-linked items running dry faster in practice, the
override is a one-line change to `needs_generation`'s threshold argument — not designed in
now, per the task's explicit permission to cut this corner.

### V3.6 API surface changes (summary)

```
POST /review/session
    body: {"size": 5|10|20, "mode": "due"|"confusion"|"weak_points" = "due"}   # NEW: mode
    -> {"questions": [...], "known_words": ["教育", "実", ...]}                # NEW: known_words

POST /review/answer                      # request/response shape UNCHANGED
    (side effect only: now also calls record_exposures — no new fields either direction)
```

No changes to `GET /grammar*` (V2 slice) or `GET /stats`. `GrammarWithProgressOut` schema
elsewhere is untouched.

### V3.7 Task breakdown (dependency-ordered, layer-tagged)

Continues the MVP (§9) / V2 (§V2.5) task-numbering convention.

| # | Layer | Task | Output | Test |
|---|---|---|---|---|
| V3.1 | DB | Migration `0003_vocabulary` — **scaffolded already**, verify against a live DB | `backend/alembic/versions/0003_vocabulary.py` | `alembic upgrade head` succeeds on Supabase branch |
| V3.2 | Backend | `app/models/vocabulary.py` (`Vocabulary`, `UserVocabulary` SQLAlchemy models mirroring the DDL) | models | `mypy` clean, round-trip unit test |
| V3.3 | Backend | `app/scripts/seed_vocabulary.py` — read external CSVs (§V3.2 column mapping), write `data/seed/vocabulary_n3.json`, upsert into `vocabulary` | script + `data/seed/vocabulary_n3.json` + report | unit tests on the CSV row parser against a few real sample rows (fixture copies, not the live external dir); manual one-time run against the owner's actual CSV directory before declaring done |
| V3.4 | Backend | `app/services/vocabulary.py` — `extract_ruby_bases`, `known_surface_forms`, `record_exposures` (ADR-15/16/19) | service | unit tests: streak increments/resets correctly, known_since sets/clears per ADR-16, exact-match doesn't false-positive on substrings |
| V3.5 | Backend | Extend `services/review.py`: `select_confusion_progress`, `select_weak_progress`, `select_due_progress_mixed` | service additions | unit tests per mode: confusion mode only returns edge-connected items, weak mode excludes `repetitions=0`, mixed mode reserves the right slot count and never duplicates an id |
| V3.6 | Backend | Wire V3.4/V3.5 into `routers/review.py`: `mode` dispatch on `POST /review/session`, `known_words` in `SessionResponse`, `record_exposures` call in `POST /review/answer`; update `schemas/review.py` | router + schema changes | integration test per mode; integration test that answering updates `user_vocabulary` rows |
| V3.7 | Backend | Extend `distractors.py` (`preferred` param) + `trigger.py` (`_fetch_confused_texts`, wire into `_build_options`) + `prompts.py`/`provider.py` (`confusable_with` prompt param) | service changes | unit test: `pick_distractors` prefers `preferred` pool before falling back; unit test `_fetch_confused_texts` returns the right partner set for a known relation fixture |
| V3.8 | Frontend | `lib/types.ts` + `lib/api.ts`: `mode` on session request, `known_words` on session response | typed client | type-checks against updated backend schema |
| V3.9 | Frontend | `services/furigana.py`-mirrored `"adaptive"` case in `FuriganaText.tsx`/`useFuriganaMode.ts`; thread `known_words` from session response down through `review/page.tsx` to every `FuriganaText` | component + page changes | manual QA: a word crosses the known threshold, next session hides its furigana in adaptive mode even outside the bold target span |
| V3.10 | Frontend | Review mode picker UI (due / confusion practice / weak points) — e.g. a small segmented control on the dashboard before "Start Review", per idea doc §15/§28's framing as distinct practice entry points | page/component | manual QA: each mode starts a session with the expected item mix |
| V3.11 | Test | QA pass across V3.6-V3.10 end to end (`qa-tester`) | bug list or sign-off | confusion mode session → weak points session → adaptive furigana over several answers → words visibly stop showing furigana loop works |
| V3.12 | Docs | Update `/llms.txt` + README for the changed `POST /review/session` contract and the new modes | docs | tech-writer sign-off |

**Parallelization:** V3.1→V3.2 (DB/model) blocks V3.3/V3.4 (need the table). V3.2 is
independent of the V2 graph work entirely — no shared tables. V3.5 (review selection) only
needs the *existing* `grammar_relation`/`grammar_progress` tables (already live), so it can
start immediately in parallel with V3.2-V3.4 — it doesn't touch `Vocabulary` at all. V3.7
(distractor/prompt bias) likewise only needs `grammar_relation`, parallel with V3.2-V3.4. Once
V3.4+V3.5 land, V3.6 (router wiring) is a short integration task. Frontend V3.8-V3.10 can
build against the frozen §V3.6 contract as soon as V3.6 is merged, same "frontend doesn't need
a live backend, just a frozen contract" pattern as MVP/V2. V3.9 (adaptive furigana rendering)
specifically only needs `known_words` to be *present* in the response (can be an empty array
until V3.3's real seed run + real usage populates `user_vocabulary` — renders identically to
`by_level` mode until then, no broken state).

### V3.8 Open items carried forward

- Kanji-CSV rows with identical `surface_form` to a word-CSV row are stored as two distinct
  `vocabulary` rows (different `entry_type`) rather than merged — both can independently
  become "known"; a single-kanji `<ruby>` span can only ever match the `entry_type='kanji'`
  row (exact match, ADR-15), so there's no real ambiguity in practice, just two counters
  tracking what is conceptually the same visual glyph in two different contexts. Not worth
  the complexity of merging them for a personal tool.
- `select_confusion_progress` quality is entirely gated on `generate_relations.py` having been
  run with a real LLM key (V2.6's open item already flagged this for the graph/browse UI;
  applies identically here) — until then, Confusion Practice sessions draw from
  `similar_form`-only heuristic-fallback edges, which is a real but weaker signal than true
  `commonly_confused` classification. No code change needed when the owner eventually adds a
  key and reruns the script — this mode automatically gets better, per the task's own framing.
- No UI surfaces `correct_exposures`/`incorrect_exposures`/vocabulary counts anywhere (no
  vocab dashboard, per this slice's scope cut) — the data is tracked and drives furigana, but
  isn't yet visible to the owner as a standalone stat. Cheap to add later (`GET
  /vocabulary/stats` mirroring `GET /stats`'s shape) if wanted.
- `weak_point_mix_ratio`/`known_streak_threshold` are hardcoded config with no owner-facing
  toggle (ADR-17) — revisit only if the owner explicitly asks to tune them, per this slice's
  "no settings UI" scope cut.

---

## V4 Slice: N4/N2 Levels & Relation Quality

Status: draft v1 · Basis: owner request 2026-09-23 (add N4/N2 levels; fix relation quality
across all levels) · Author: architect agent · Date: 2026-09-23

MVP + V2 (Grammar Graph/Browse) + V3 (Adaptive Practice & Vocabulary) are shipped. This slice
adds two things: (1) two new JLPT levels of grammar content (N4: 142 items, N2: 130 items
across Shin Kanzen Master's 26 lessons), and (2) a hand-curated relation-quality pass that
covers all three levels plus cross-level edges, replacing the existing 733 N3 heuristic edges
where curation now covers a pair. **Additive only** — no existing table, endpoint, or
algorithm from MVP/V2/V3 is redesigned. ADR numbering continues from ADR-20.

**Verified up front, per the task's own instruction to only scaffold a migration if actually
needed: no migration is required for this slice.** `grammar.level` is already `TEXT NOT NULL
DEFAULT 'N3'` (§3 DDL) — a free-text column, not an enum, already populated per-row by
`seed_import.py`. `grammar_relation.source` already has `'manual'` in its
`grammar_relation_source` Postgres enum (§V2.1 DDL, `app/models/grammar_relation.py`), which
is exactly what curated edges need. Both existing indexes (`ix_grammar_level`, the
`grammar_relation` FK indexes) already support the new query patterns below with no DDL
change.

### V4.1 Authored-content JSON schema (N4 / N2 grammar)

The Anki-export intermediate format (`n3_grammar_anki_export.json` → `connection_formation`
text parsing, per §4) exists only because the N3 deck came out of Anki in that shape. N4/N2
have no Anki source — they're authored directly from the two JLPT lists in this prompt (N4:
apieceofsushi.com flat list; N2: Shin Kanzen Master's own 26 lessons) by a content-generation
agent, so the target format should be the **DB-ready shape itself**, not an intermediate one
that then needs a second parsing pass.

**Files**: `data/seed/n4_grammar_authored.json`, `data/seed/n2_grammar_authored.json` — one
file per level, top-level `level` field applies to every item in the file (no per-item
`level` field, avoids drift).

```json
{
  "level": "N4",
  "items": [
    {
      "key": "n4_012_aida",
      "expression_html": "<ruby>日本<rt>にほん</rt></ruby>にいる<b>間</b>に<ruby>一度富士山<rt>いちどふじさん</rt></ruby>に<ruby>登<rt>のぼ</rt></ruby>ってみたい。",
      "reading": "にほんにいる<b>あいだ</b>に いちど ふじさんに のぼってみたい。",
      "meaning_ru": "Пока я в Японии, хочу хоть раз подняться на Фудзи.",
      "pattern_text": "Паттерн: [期間/状態] + 間（に） (N4)\nЗначение: В течение периода ... / пока состояние не изменилось, сделай ...",
      "formation_rules": [
        {"pos": "сущ.の", "form_label": "сущ.の", "example_html": "<ruby>休<rt>やす</rt></ruby>みの<b>間</b>に"},
        {"pos": "гл.ている", "form_label": "гл.ている", "example_html": "<ruby>寝<rt>ね</rt></ruby>ている<b>間</b>に"}
      ],
      "target_construction": "間に",
      "tags": ["N4", "time", "lesson:na"]
    }
  ]
}
```

Field-by-field:

| Field | Type | Notes |
|---|---|---|
| `key` | string | **Stable slug, unique within the file** (`"n4_012_aida"`, `"n2_007_ni_saishite"`). Never renamed once imported — the import script derives the DB row's `source_note_id` deterministically from `(level, key)`, so renaming a key creates a *new* row instead of updating the old one (documented as ADR-21 below). This is also the identifier the relation-curation file (§V4.3) uses to reference N4/N2 items. |
| `expression_html` | string | Full example sentence, `<ruby><rt>` furigana + `<b>...</b>` around the target construction — same markup convention as the N3 deck (§3's `expression_html`) and the AI-generation prompt (§7.3), so `FuriganaText.tsx`/`services/furigana.py` need zero changes to render it. |
| `reading` | string | Kana reading of the sentence, `<b>` around the target — mirrors N3's `reading` field exactly. |
| `meaning_ru` | string | Russian translation of the pattern's meaning. |
| `pattern_text` | string | Free-text rule + meaning, same `"Паттерн: ... \nЗначение: ..."` convention as N3 so `GrammarDetailOut`'s rendering needs no branching by level. |
| `formation_rules` | array of `{pos, form_label, example_html}` | **Authored directly in DB-ready shape** — this is the simplification vs. N3's `connection_formation` text-parsing step; no `→`-delimited line format, no parser needed on the N4/N2 path. |
| `target_construction` | string | Plain text (no markup) of the construction being tested — must literally appear (after tag-stripping) in `expression_html`; the import script checks this and flags a mismatch in its report rather than failing the batch (mirrors ADR-6b's "don't hard-fail on one bad row" posture). |
| `tags` | array of strings | **Populated meaningfully this time** (unlike N3's ADR-4 all-empty tags): always includes the level tag (`"N4"`/`"N2"`) plus one semantic category from a small fixed taxonomy (reuse `Conditionals/Causality/Contrast/Time/Quantity/Modality/Honorifics/Comparison/Hearsay/Emphasis/...` per idea doc §46) — cheap forward-compat groundwork for a future category browse view, not required by any endpoint in this slice. For N2 specifically, also include a `lesson:NN` tag (zero-padded lesson number, `"lesson:01"`..`"lesson:26"`) since Shin Kanzen Master's own lesson structure is real curriculum data already given in the source list — free to capture now even though lesson-based curriculum browsing itself stays deferred (SPEC §4 "Явно вне MVP"). N4 items get `"lesson:na"` (the source list is flat, no lesson structure) — kept for schema uniformity, not for filtering. |

`expression_clean` (plain JP, no markup) is **not authored** — the import script derives it
by stripping tags from `expression_html` (reusing `strip_tags` from `seed_import.py`, §4),
same as how N3's `expression_clean` and `expression_html` already have to agree; removing the
redundant authored field removes one way content-agent output could drift from the markup.

**[ADR-21] Synthetic `source_note_id` via deterministic hash, not a manual counter.**
`grammar.source_note_id` is `BIGINT UNIQUE NOT NULL` and is what both `seed_import.py` and
this slice's importer use as the idempotency key (upsert-by-`source_note_id`, same pattern,
zero special-casing). N4/N2 items have no Anki note id to reuse. Decision: derive it as
```python
source_note_id = int(hashlib.sha256(f"{level}:{key}".encode()).hexdigest()[:15], 16)
```
— a deterministic 60-bit positive integer from `(level, key)`. This needs no central registry
or manual index bookkeeping (a content agent authoring 142+130 items shouldn't have to track
a shared counter across two files), is trivially idempotent (same `key` always hashes to the
same id, so re-running the import on an edited JSON file updates the same row), and collides
with real Anki `note_id`s (~13-digit timestamps, ~1.7×10¹²) or with each other only at
cryptographic-hash-collision probability — a non-concern at this scale. The one real failure
mode is a content agent renaming a `key` after first import (creates an orphan old row + a new
row) — documented as a authoring-time discipline rule, not solved with extra code for a
personal tool.

### V4.2 Import path: `seed_import_authored.py`

New script, **not an extension of `seed_import.py`** (kept separate because the two scripts'
inputs are shaped too differently — Anki-JSON-with-a-text-parser vs. DB-ready-JSON — but it
**imports and reuses** `seed_import.py`'s helpers rather than duplicating them: `strip_tags`,
`build_blanked_sentence_html`, `check_rt_payloads_are_kana`, and — critically —
`import_seed_questions`, which already operates over **every** `Grammar` row lacking a `SEED`
question, regardless of level, and is already idempotent. No changes to `seed_import.py`
itself are needed; N4/N2 grammar rows just become additional input to that same
already-generic function once they exist in the `grammar` table.

```
uv run python -m app.scripts.seed_import_authored
    # defaults to data/seed/n4_grammar_authored.json + data/seed/n2_grammar_authored.json
uv run python -m app.scripts.seed_import_authored path/to/custom.json [more.json ...]
```

Per file, per item:
1. Compute `source_note_id` per ADR-21.
2. Derive `expression_clean = strip_tags(expression_html)`.
3. Validate `target_construction` (stripped) appears in `expression_clean`; mismatch →
   append to the report as `{"key": ..., "type": "target_construction_mismatch"}`, import
   proceeds anyway (same defensive posture as ADR-6/ADR-6b).
4. Run `check_rt_payloads_are_kana(expression_html)` — same anomaly detector N3 import already
   uses, reused verbatim (a content agent can make the same ruby-scope mistakes a human Anki
   editor did).
5. Upsert `Grammar` by `source_note_id` — insert path also creates the paired
   `GrammarProgress(status=NEW, next_review=now())` row (same as §4's existing logic); update
   path touches every content field (idempotent re-import if the content agent revises an
   item) but **never touches `grammar_progress`** (an edit to wording shouldn't reset SRS
   state on an item the owner has already been reviewing).
6. After all items in all files are upserted: call `seed_import.py::import_seed_questions(db)`
   once — it naturally picks up every new N4/N2 `Grammar` row (no `SEED` question yet) and
   builds one seed question each via the existing blank-generation + `pick_distractors` logic,
   completely unmodified.

**Must not touch/duplicate N3 rows**: guaranteed structurally, not by an exclusion check —
this script never reads `n3_grammar_anki_export.json`, and ADR-21's hash namespace can't
collide with N3's real Anki `note_id`s (13 digits vs. this script's 15-hex-digit/60-bit
outputs, astronomically distinct ranges even before considering hash collision odds).

**Idempotent**: re-running on unchanged files no-ops (upsert to identical values, no new
`SEED` questions since `import_seed_questions` already skips grammar ids with an existing seed
question); re-running after a content edit updates the `Grammar` row's content fields without
touching progress or without creating a duplicate `Question`.

Report: `backend/app/scripts/seed_import_authored_report.json`, same shape as
`seed_import_report.json` (§4) — `{total, inserted, updated, anomalies, seed_questions}` — one
block per input file plus a combined `seed_questions` summary from the single
`import_seed_questions` call at the end.

### V4.3 Curated relations: schema + import script

**Problem being solved**: the existing 733 N3 edges are 100% `source='heuristic'` (§V2.2 —
`generate_relations.py`'s no-API-key fallback path, since `ANTHROPIC_API_KEY`/
`OPENAI_API_KEY` are both empty in `backend/.env`, confirmed). Heuristic scoring (shared
function-word stem / meaning-keyword Jaccard / shared-kanji rarity, `relation_heuristics.py`)
is a *candidate filter*, not a semantic judgement — every one of those 733 rows was written by
`_fallback_relation_type`'s crude 3-way rule (stem match → `similar_form`; else Jaccard ≥ 0.3 →
`similar_meaning`; else → `related`), not by anything that actually understood the grammar.
That's the "noise" the owner is asking to fix.

**Decision: hand-authored curated edges, same content-agent pattern as V4.1's grammar
content, not a second LLM-classification attempt.** No LLM key is configured in this
environment either way (`generate_relations.py`'s LLM path literally cannot run here), and the
owner's own request frames this as something "a content agent that reasons about real semantic
relationships" should author directly — i.e. treat relation quality as authored content, the
same posture as V4.1 treats grammar content, not as a second automated-classification pipeline
problem.

**File(s)**: `data/seed/relations_curated_*.json` (glob pattern — the import script accepts
multiple files so the curation agent can split its ~1,000+ edges into manageable chunks by
scope rather than authoring one giant file: suggested split
`relations_curated_n3.json` / `relations_curated_n4.json` / `relations_curated_n2.json` /
`relations_curated_cross.json`, but the script doesn't care about filenames, just the glob).

```json
{
  "edges": [
    {
      "a": {"level": "N4", "key": "n4_012_aida"},
      "b": {"level": "N3", "target_construction": "うちに"},
      "relation_type": "advanced_version",
      "direction": "b_to_a",
      "strength": 0.85,
      "note": "N4の「間に」はN3「うちに」の基礎形。「うちに」の方が状態の変化への焦点が強い — N3's うちに is the more nuanced/advanced form of the same 'while the state holds, do X' idea."
    },
    {
      "a": {"level": "N3", "target_construction": "わけだ"},
      "b": {"level": "N3", "target_construction": "わけではない"},
      "relation_type": "commonly_confused",
      "strength": 0.95,
      "note": "わけだ affirms a logical conclusion; わけではない negates the conclusion, not the premise — classic N3 confusion pair."
    }
  ]
}
```

**Reference resolution** (`a`/`b`, each an object identifying one grammar item without
needing a DB UUID at authoring time — the curation agent works purely from the JSON content
files, same as V4.1):
- `{"level": "N4"|"N2", "key": "..."}` → resolved by recomputing ADR-21's hash and looking up
  `Grammar.source_note_id`. Exact, unambiguous, same mechanism the importer itself uses.
- `{"level": "N3", "target_construction": "..."}` → resolved by
  `Grammar WHERE level='N3' AND target_construction=<text>`. N3's `target_construction` values
  are effectively unique per item (extracted from each Anki card's own `<b>` span); the 3 rows
  with an empty `target_construction` (ADR-6b) can't be referenced this way — an edge citing
  one of those must instead use `{"level": "N3", "expression_clean": "..."}` as a fallback key
  (checked second if `target_construction` is absent from the reference object). Either
  reference type resolving to zero or multiple rows is **not a hard failure** — the edge is
  skipped and logged in the report (`"type": "unresolved_reference"`), consistent with this
  slice's whole "flag, don't block" posture (ADR-6/ADR-6b/ADR-21's own mismatch handling).

**Script**: `backend/app/scripts/import_curated_relations.py`

```
uv run python -m app.scripts.import_curated_relations
    # defaults to glob data/seed/relations_curated_*.json
uv run python -m app.scripts.import_curated_relations --purge-remaining-heuristic
    # see ADR-22
```

1. Load + merge all matching files' `edges` arrays.
2. Resolve `a`/`b` → `Grammar` rows (skip + log unresolved, per above).
3. Reject self-loops (`a` resolves to the same row as `b`) — same guard as the DB's own
   `CHECK (grammar_id <> related_grammar_id)`, checked in Python first so it lands in the
   report instead of surfacing as a raw DB `IntegrityError`.
4. Canonicalize direction per the existing ADR-11 rules (symmetric types → sort by
   `str(uuid)`; directional types → `direction: "a_to_b"|"b_to_a"` picks which resolved id is
   `grammar_id` vs. `related_grammar_id"`), reusing `_canonicalize_symmetric` imported from
   `generate_relations.py` rather than reimplementing it.
5. **[ADR-22] Precedence: curated (`manual`) always wins over both `heuristic` and
   `llm_classified` for the exact same unordered pair, but only for pairs the curated file
   actually addresses** — the owner's own recommendation in the request, taken literally: "a
   curated edge covering a pair replaces the heuristic edge for that pair"; pairs the curation
   agent didn't get to keep whatever they had before (still noisy where uncurated, but not
   silently deleted — losing an edge entirely is worse than a mediocre one for the graph view's
   connectivity). Mechanism: for every resolved pair, delete any existing `grammar_relation`
   row for that unordered `(grammar_id, related_grammar_id)` pair **regardless of its
   `relation_type` or `source`** (a curated edge fully supersedes whatever heuristic/LLM
   guesses existed for that pair, even if the curated relation_type differs from the old one —
   e.g. heuristic said `related`, curation says `commonly_confused`: the old `related` row is
   removed, not left alongside). Extends `generate_relations.py`'s existing
   `_delete_stale_heuristic_rows` pattern (imported and generalized to also match
   `llm_classified`-sourced rows, since none exist today but the logic should be correct if the
   owner ever does configure a key later). Then upsert the curated row with
   `source='manual'`, `prompt_version=None`.
   - **Optional full purge** (`--purge-remaining-heuristic` flag, off by default): after the
     curated pairs are processed, delete every *remaining* `source='heuristic'` row entirely
     (not just the ones curation touched). This is offered because the owner's ask was "ALL
     edges genuinely good quality" — if the curation agent's coverage turns out comprehensive
     enough that the owner would rather have *no* edge than a known-noisy heuristic one for the
     leftover pairs, this flag gives a clean way to say so without re-running the whole script
     differently. Default is **off** (matches the owner's own literal recommendation of
     "remove heuristic only where superseded") so a first run never silently drops graph
     connectivity the curation agent didn't get around to replacing.
6. Idempotent: rerun-safe via the same `ON CONFLICT (grammar_id, related_grammar_id,
   relation_type) DO UPDATE` upsert (`uq_grammar_relation_edge`) as `generate_relations.py`
   already uses.
7. Report: `import_curated_relations_report.json` —
   `{edges_read, resolved, unresolved: [...], self_loops_rejected, heuristic_rows_replaced,
   llm_rows_replaced, inserted, updated, count_by_relation_type, purge_remaining_heuristic_ran,
   heuristic_rows_purged}`.

**Cross-level edges** are handled with zero special-casing — a `grammar_relation` row doesn't
care whether `grammar_id`/`related_grammar_id` point at same-level or different-level `Grammar`
rows; `direction`/`relation_type` semantics (ADR-11) are level-agnostic. `prerequisite`/
`advanced_version` are expected to be the most common cross-level types in practice (e.g. N4's
そうだ(伝聞/様態) as `prerequisite` to N3/N2's more advanced hearsay forms, per the task's own
example), but nothing in the schema restricts any of the 7 types from spanning levels.

**Scope guidance for the curation task** (not executed here, per instruction #6 — for the
ai-engineer agent that runs this task): aim for comprehensive coverage of (a) every obvious
function-word-family cluster within each level (the わけ/ばかり/ながら/... stems already
enumerated in `relation_heuristics.py::FUNCTION_WORD_STEMS` are a ready-made checklist — for
each stem-family, curate the *actual* relation type between its members instead of trusting
the heuristic's guess), (b) well-known cross-level JLPT confusion/progression pairs (N4→N3→N2
forms of the same underlying meaning, e.g. そうだ/ようだ/らしい's three-level spread), and
(c) enough coverage that few N4/N2 items are left with zero relations. A precise edge-count
target isn't prescribed — quality and real coverage over a specific number.

### V4.4 API surface changes

```
GET /grammar?level=&q=&status=&tag=&limit=&offset=
    level  - NEW, optional. Exact match against grammar.level ("N3"|"N4"|"N2"). Omitted =
             all levels (backward-compatible default — existing MVP/V2/V3 callers that never
             passed `level` keep returning everything, now spanning 3 levels instead of 1
             once N4/N2 are seeded).
    (q/status/tag/limit/offset unchanged from §V2.3)

POST /review/session
    body: {"size": 5|10|20, "mode": "due"|"confusion"|"weak_points" = "due",
           "level": "N3"|"N4"|"N2"|null = null}          # NEW: level
    level applies as an additional filter on whichever selection function `mode` dispatches to
    (`select_due_progress_mixed`/`select_confusion_progress`/`select_weak_progress` in
    `services/review.py`, all three already query through `grammar_progress` joined to
    `grammar` — one extra `.where(Grammar.level == level)` clause per function when `level` is
    not null, same pattern as the existing `mode` dispatch, no new service). `null` (default)
    = due/weak/confusion selection spans all levels together, matching the task's "don't
    over-build a full multi-curriculum system" steer — a due N4 item and a due N3 item compete
    for the same session slots exactly as two due N3 items would today; level is an opt-in
    narrowing filter for a focused practice session, not a mandatory selector.

GET /stats?level=
    level  - NEW, optional, same semantics as above. Omitted = combined stats across all
             levels (unchanged existing behavior — no breaking change for the current
             Dashboard). `?level=N4` scopes every count (`due_count`, `new_count`, ...,
             `recall_pct`) to that level's `grammar_progress` rows only.
    StatsOut gains one field: `total_items: int` — replaces the frontend's hardcoded
    `TOTAL_GRAMMAR_ITEMS = 205` constant (§stats/page.tsx) with a real count reflecting
    whichever `level` filter (or all 3 levels combined) was requested. **[ADR-23]** Chosen
    over adding a separate `/stats/by-level` endpoint: a personal-tool dashboard with 3 levels
    can afford 3 small parallel `GET /stats?level=X` calls if it wants a per-level breakdown
    (each one is already a handful of cheap aggregate queries against ≤500 rows total) — not
    worth a second endpoint/response shape for this data volume, matching this slice's
    "proportionate, don't over-build" instruction.
```

Schema changes: `backend/app/schemas/stats.py` — `StatsOut` gains `total_items: int`.
`backend/app/schemas/review.py` — `SessionRequest` gains `level: Literal["N3", "N4", "N2"]
| None = None`. `backend/app/routers/grammar.py` — `list_grammar` gains the `level` query
param, applied as a `Grammar.level == level` where-clause alongside the existing `q`/`status`/
`tag` filters (same pattern, no new query-building logic). No changes to `GrammarOut`/
`GrammarWithProgressOut`/`GrammarDetailOut` (`level` field already exists on all of them since
MVP §3).

### V4.5 Frontend changes

**No new dependencies** — same posture as V2.4/V3's frontend sections. A small reusable
`components/LevelSelector.tsx` (segmented control: `N3 | N4 | N2 | Все`) is the one new
component; everywhere else is wiring the existing pages to an optional `level` param.

| File | Change |
|---|---|
| `src/lib/types.ts` | Add `export type GrammarLevel = "N3" \| "N4" \| "N2";`. `GrammarListParams` gains `level?: GrammarLevel`. `SessionRequest` gains `level?: GrammarLevel`. `Stats` gains `total_items: number`. |
| `src/lib/api.ts` | Thread `level` through `fetchGrammarList`, `startReviewSession`, `fetchStats` request builders (append `?level=` when present, same as the existing `q`/`status`/`tag`/`mode` params). |
| `src/components/LevelSelector.tsx` | **New.** Segmented control, controlled component (`value: GrammarLevel \| "all"`, `onChange`). No new state library — persisted via the same `localStorage` pattern `useFuriganaMode.ts` already established (§V3.4), key e.g. `jp-grammar:selected-level`, default `"all"`. |
| `src/components/AppHeader.tsx` | Replace the hardcoded `"JP Grammar · N3"` span with `<LevelSelector>` (global level context for the session — Dashboard/Grammar-list/Review-start all read the same persisted value unless a page-local override is used, e.g. the Grammar list page's own filter chips per below). |
| `src/app/layout.tsx` | Metadata `description: "Personal N3 grammar spaced-retrieval trainer."` → `"Personal JLPT grammar spaced-retrieval trainer (N4–N2)."` — copy fix only, no functional change. |
| `src/app/page.tsx` (Dashboard) | Heading `"Тренажёр грамматики N3"` → `"Тренажёр грамматики"` (level now shown via the header selector, not baked into the page title). `GET /stats` call passes the currently-selected level (or omits `level` for "Все" = combined). "Start Review" CTA passes the same `level` into `POST /review/session`. |
| `src/app/stats/page.tsx` | Remove the hardcoded `const TOTAL_GRAMMAR_ITEMS = 205` constant entirely; use the new `Stats.total_items` field from the API response instead. Copy `"N3 grammar (Anki seed)"` → dynamic, e.g. `` `${level} grammar` `` or `"Grammar (all levels)"` when combined. |
| `src/app/grammar/page.tsx` | Copy `"Все конструкции N3 · просмотр вне сессий повторения"` → `"Все конструкции · просмотр вне сессий повторения"`. Add level filter chips (`N3 / N4 / N2 / Все`) reusing the exact same chip UI pattern already used for the `status` filter on this page, wired to `GrammarListParams.level`. |
| `src/app/review/page.tsx` | No structural change — already receives whatever `SessionRequest` the Dashboard/mode-picker (§V3.10) constructed; `level` just rides along as one more optional field, same as `mode` did in V3. |

### V4.6 Task breakdown (dependency-ordered, layer-tagged)

Continues the MVP (§9) / V2 (§V2.5) / V3 (§V3.7) task-numbering convention.

| # | Layer | Task | Output | Test | Depends on |
|---|---|---|---|---|---|
| V4.1a | AI (content) | Author `data/seed/n4_grammar_authored.json` — 142 items per §V4.1 schema, from the N4 list given in the owner's prompt (do not re-derive from training knowledge — that list is the authoritative inventory). Match N3's depth: formation rules per applicable part of speech, one ruby-marked example sentence, meaningful `tags`. | `data/seed/n4_grammar_authored.json` | JSON validates against the schema (script from V4.2 can `--dry-run` parse without DB write); spot-check 10 random items for markup correctness | — |
| V4.1b | AI (content) | Author `data/seed/n2_grammar_authored.json` — 130 items across all 26 Shin Kanzen lessons per §V4.1 schema (incl. `lesson:NN` tags), from the N2 list given in the owner's prompt. | `data/seed/n2_grammar_authored.json` | same as V4.1a, plus: every item has a `lesson:01`..`lesson:26` tag matching its source lesson | — (parallel with V4.1a) |
| V4.2 | Backend | `backend/app/scripts/seed_import_authored.py` per §V4.2 — reuses `seed_import.py` helpers, does not modify it | script | unit tests: `source_note_id` hash determinism, upsert idempotency, mismatch flagging on a deliberately-broken fixture item; integration test importing a small fixture file end-to-end | — (code-only, can be written in parallel with V4.1a/b, integration-tested once they land) |
| V4.3 | Backend | Run `seed_import_authored.py` against the real N4/N2 files (V4.1a/V4.1b) | populated `grammar`+`grammar_progress`+seed `question` rows for 142+130 items | report shows 0 (or a small, explainable) count of `target_construction_mismatch`/`malformed_rt_payload` anomalies; row counts match 142/130 | V4.1a, V4.1b, V4.2 |
| V4.4 | AI (content) | Curate `data/seed/relations_curated_*.json` per §V4.3 (within-N4, within-N3, within-N2, cross-level), using `n3_grammar_anki_export.json` + the two new authored files as source material | `data/seed/relations_curated_*.json` | spot-check known confusion families (わけ, ばかり, そうだ) resolve correctly against the reference scheme; unresolved-reference count is near-zero on a dry parse | V4.1a, V4.1b (needs final N4/N2 `key`/`target_construction` values to reference; does not need V4.3's DB import to have run) |
| V4.5 | Backend | `backend/app/scripts/import_curated_relations.py` per §V4.3 | script | unit tests: reference resolution (both key-based and target_construction-based, incl. the `expression_clean` fallback for ADR-6b's 3 empty-target rows), precedence/deletion logic (ADR-22), idempotent rerun; integration test against a small fixture edge set | — (code-only, parallel with V4.4) |
| V4.6 | Backend | Run `import_curated_relations.py` against the real curated file(s) (V4.4) against the DB (needs V4.3's N4/N2 rows to exist for cross-level edges to resolve) | live `grammar_relation` rows, `source='manual'` where curated | report: heuristic-rows-replaced count > 0, unresolved-reference count near-zero, spot-check the graph view (once V4.9 frontend lands, or via `GET /grammar/{id}/relations` directly) on a few known items | V4.3, V4.4, V4.5 |
| V4.7 | Backend | `GET /grammar?level=`, `POST /review/session` `level` field, `GET /stats?level=` + `StatsOut.total_items` per §V4.4 | router/schema changes | integration tests: level filter narrows list/session/stats correctly; omitted `level` preserves exact current (all-levels) behavior for backward compat | — (independent of content tasks, can start immediately) |
| V4.8 | Test | Unit + integration test pass for V4.2/V4.5/V4.7 | test files | `pytest` green | V4.2, V4.5, V4.7 |
| V4.9 | Frontend | `LevelSelector.tsx` + `lib/types.ts`/`lib/api.ts` wiring per §V4.5 | component + typed client changes | type-checks against updated backend schema | V4.7 (frozen contract) |
| V4.10 | Frontend | Wire `LevelSelector` into `AppHeader`, `Dashboard`, `Grammar list` filter chips, `Stats` page (`total_items`), copy fixes across `layout.tsx`/`page.tsx`/`grammar/page.tsx`/`stats/page.tsx` per §V4.5 table | page/component changes | manual QA: switching level filters the grammar list and review-session composition; stats page shows the real item count (307 combined once N4/N2 land, no hardcoded 205) | V4.9 |
| V4.11 | Test | QA pass: seed N4/N2 → confirm reviewable end-to-end at each level, confirm curated relations render in the graph/detail "Compare with…" view, confirm level filter/selector across Dashboard/Grammar-list/Review/Stats (`qa-tester`) | bug list or sign-off | full flow: pick N4 in header → Dashboard shows N4-only due count → start review → N4 questions only → grammar list filtered to N4 → detail page for an N4 item shows curated relations incl. any cross-level ones | V4.3, V4.6, V4.10 |
| V4.12 | Docs | Update `/llms.txt` + README for `?level=` params on all 3 endpoints, the two new seed scripts, and the curated-relations script | docs | tech-writer sign-off | V4.7, V4.2, V4.5 |

**Parallelization for the orchestrator**: V4.1a and V4.1b (content) run fully in parallel —
independent files, independent agents. V4.2 and V4.7 (backend, code-only) can start
immediately in parallel with V4.1a/b since they don't need the content to exist yet, only to
be tested against it once it lands (same "frontend/backend don't need live content, just a
frozen contract" pattern already established in every prior slice). V4.4 (relations curation)
is the one hard content-after-content dependency the task called out explicitly — it needs
V4.1a/b's *final* `key`/`target_construction` values to write valid references against, so it
should not start until those two files are considered done (not merely started). V4.5
(curated-relations import script) is code-only and parallel with V4.4, same as V4.2 is
parallel with V4.1a/b. V4.9-V4.10 (frontend) can start as soon as V4.7's contract is frozen
(already frozen in §V4.4 above), independent of whether the real content/curation runs
(V4.3/V4.6) have happened — an empty or partially-seeded DB renders correctly, same posture
as every prior slice's frontend task.

### V4.7 Open items carried forward

- Full elimination of *all* 733 pre-existing N3 heuristic edges isn't guaranteed by this
  slice — only pairs the curation agent's file actually addresses get their heuristic edge
  replaced (ADR-22's literal reading of the owner's own recommendation). The
  `--purge-remaining-heuristic` flag exists for a deliberate follow-up pass if the owner wants
  a hard guarantee of zero remaining heuristic-sourced edges after reviewing V4.6's report.
- N3's `tags` stay empty per ADR-4 — this slice populates tags only for newly-authored N4/N2
  content, doesn't retroactively tag the existing 205 N3 items. Cheap follow-up if wanted
  later (a small content task, not a schema change).
- `level`-scoped session composition (V4.4) doesn't add any cross-level-aware weighting (e.g.
  "prioritize N4 review before allowing N2 due items") — `null`/omitted `level` just pools
  everything together by due-ness exactly as MVP's single-level due-selection already did.
  Explicit per-level pacing/gating is out of scope, consistent with SPEC's original deferral
  of "lesson-based curriculum"/multi-level sequencing to well beyond this personal tool's
  current scope.
- `GET /stats?level=` triggering 3 parallel frontend calls for an "all levels, broken down"
  dashboard view (rather than a dedicated `/stats/by-level` endpoint, ADR-23) should be
  revisited only if it turns out to feel slow in practice — not expected at this data volume
  (≤500 total grammar rows across all 3 levels).
