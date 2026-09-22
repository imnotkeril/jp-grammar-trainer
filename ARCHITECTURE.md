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
