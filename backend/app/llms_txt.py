from __future__ import annotations

"""Static content for GET /llms.txt.

Kept as a plain string (not a file read from disk) so it ships inside the app package
regardless of working directory / deploy target. Update this whenever a route or schema
in app/routers/* or app/schemas/* changes — it must stay in sync with the real API surface.
"""

LLMS_TXT = """\
# JP Grammar Trainer API

> Personal, single-user Japanese JLPT grammar spaced-retrieval trainer backend (N4/N3/N2).
> No auth — every row belongs to the single owner. FastAPI + PostgreSQL. See
> /ARCHITECTURE.md in the project repo for full system design, DB schema, SRS algorithm, and
> AI generation pipeline.

Base URL: this server's origin (e.g. http://localhost:8000 in dev). All endpoints return JSON
except this file. CORS is restricted to the origins in CORS_ALLOWED_ORIGINS.

## Endpoints

### GET /health
Liveness check.
Response 200: `{"status": "ok"}`

### GET /grammar
Browsable, filterable list of seeded grammar items across all JLPT levels (N4/N3/N2), ordered
by original Anki note id (N3) / import order (N4/N2).
**V2 breaking change vs MVP**: now returns a `{items, total}` wrapper (was a bare array).
Query params (all optional):
```
level   - V4, NEW. Exact match against grammar.level: "N3"|"N4"|"N2". Omitted = all levels
          (backward compatible — pre-V4 callers keep getting everything, now spanning 3
          levels instead of 1 once N4/N2 are seeded).
q       - case-insensitive substring match across expression_clean, reading, meaning_ru,
          pattern_text (Postgres ILIKE, OR'd across the four columns)
status  - filter by grammar_progress.status: new|learning|review|mastered
tag     - tag containment filter. N3 items have no tags (ADR-4); N4/N2 items (V4) are tagged
          with their level plus a semantic category, and N2 items additionally with
          `lesson:01`..`lesson:26`.
limit   - default 205 (i.e. "return everything" by default, max 1000). Raise this if
          requesting all levels combined once N4/N2 are seeded (up to ~477 rows).
offset  - default 0
```
Response 200:
```
GrammarListOut = { items: GrammarWithProgressOut[], total: number }
GrammarWithProgressOut = GrammarOut + {
  status: string,            # new|learning|review|mastered
  next_review: string (ISO datetime),
  interval_days: number,
  recall_score: number,
}
GrammarOut = {
  id: string (uuid),
  expression_html: string,       # original <ruby>/<rt>/<b> markup, target construction bolded
  expression_clean: string,      # plain Japanese, no markup
  reading: string,                # kana reading
  meaning_ru: string,             # Russian translation
  pattern_text: string,           # rule statement + meaning
  formation_rules: FormationRule[],
  level: string,                  # "N3"|"N4"|"N2" (V4 adds N4/N2 alongside MVP's N3)
  tags: string[],                 # empty for N3 (ADR-4); populated for N4/N2 (V4, see above)
  target_construction: string,    # plain text of the grammar point being tested
}
FormationRule = { pos: string, form_label: string, example_html: string }
```

### GET /grammar/relations
Bulk edge list for the graph view — ALL relation edges in one call (V2). Register this route
is matched before `/grammar/{grammar_id}` (fixed path segment takes priority).
Response 200:
```
GrammarRelationEdgeOut[] = [{
  grammar_id: string (uuid),
  related_grammar_id: string (uuid),
  relation_type: string,     # similar_meaning|similar_form|commonly_confused|opposite|
                              # prerequisite|advanced_version|related
  direction: "symmetric" | "outgoing",   # relative to grammar_id (the stored "from" side)
  strength: number,           # 0..1
}, ...]
```

### GET /grammar/{grammar_id}
Single grammar item by id, with progress and relations embedded (V2: previously bare
`GrammarOut`, no progress/relations).
Path param: `grammar_id` (uuid)
Response 200:
```
GrammarDetailOut = GrammarWithProgressOut + {
  relations: GrammarRelationOut[]
}
GrammarRelationOut = {
  relation_type: string,
  direction: "symmetric" | "outgoing" | "incoming",   # relative to THIS grammar item
  strength: number,
  source: string,             # heuristic|llm_classified|manual
  note: string | null,        # 1-line justification, shown as a tooltip
  related_grammar: {
    id: string (uuid), expression_clean: string, reading: string,
    meaning_ru: string, target_construction: string,
  },
}
```
Response 404: `{"detail": "Grammar item not found"}`

### GET /grammar/{grammar_id}/relations
Standalone relations-only fetch for one grammar item (V2) — same array as the `relations`
field above, for callers that don't need the full grammar payload.
Path param: `grammar_id` (uuid)
Response 200: `GrammarRelationOut[]` (see above)
Response 404: `{"detail": "Grammar item not found"}`

### POST /review/session
Start a review session: selects due items (overdue first, then new), serves one question per
item, and fires background AI-generation for any item running low on unused questions
(silently skipped if no LLM API key is configured — seed questions still serve).
Request body:
```
SessionRequest = {
  size?: 5 | 10 | 20,                          # default 10
  mode?: "due" | "confusion" | "weak_points",  # default "due"
  level?: "N5" | "N4" | "N3" | "N2" | "N1",    # V4, NEW. default null = all levels pooled
  family_of?: string,                          # grammar id; only with mode "confusion" (else 422).
                                               # Limits the session to that item's relation family
                                               # (connected component over all relation edges).
}
```
- `due` — overdue items first, then new (MVP behavior). For `size > 5`, ~20% of slots are
  mixed in from the user's weakest items regardless of due date (ADR-17).
- `confusion` — only items connected by a `commonly_confused`/`similar_form` edge in
  `grammar_relation` (V2 graph), ranked by strongest edge. Empty if no such edges exist yet
  (e.g. `generate_relations`/`import_curated_relations` hasn't been run).
- `weak_points` — items with `repetitions > 0`, ordered by lowest
  `application_score + discrimination_score` first. Excludes never-reviewed items (no signal
  yet to call them "weak"). Both scores are real per-item EMAs (see `POST /review/answer`
  below) — an item that has repetitions but no *informative* attempts yet for one dimension
  simply keeps that dimension's neutral 0.5 default rather than a misleadingly low value.
- `level` (V4) narrows whichever mode above to a single JLPT level's `grammar_progress` rows
  (for `confusion` mode, both sides of a candidate edge must be in that level). `null`/omitted
  (default) pools all levels together exactly as before V4 — e.g. a due N4 item and a due N3
  item compete for the same session slots. Not a mandatory selector, opt-in only.
Response 200:
```
SessionResponse = { questions: QuestionOut[], known_words: string[] }
QuestionOut = {
  id: string (uuid),
  grammar_id: string (uuid),
  sentence_with_blank_html: string,   # ruby-preserving sentence with target replaced by ___
  options: QuestionOption[],           # always 4, one correct + 3 distractors, pre-shuffled
}
QuestionOption = { key: string, text: string }   # key is "A".."D"
```
`known_words` is the surface-form list (V3 vocabulary) the caller should strip furigana from
when rendering in `"adaptive"` furigana mode — the backend does NOT pre-strip the HTML, the
client applies this list against `<ruby>base<rt>reading</rt></ruby>` spans itself (see
`FuriganaText.tsx`'s `stripKnownWords`, which mirrors `furigana.py`'s `strip_known_words`).
Note: an item with no valid question yet available (generation not landed) is skipped for
this round and stays due for the next session — the response may contain fewer items than
`size`.

### POST /review/answer
Submit an answer to a served question. Records the attempt, runs the SRS scheduler to update
that grammar item's progress (including `recall_score` and, when the served question is
"informative" for that dimension, `application_score`/`discrimination_score` — see below), and
returns a contrastive explanation.

`application_score` and `discrimination_score` (SPEC.md idea doc §28's 4 skill dimensions,
alongside `recall_score`) are rolling EMAs (same `alpha=0.2` update as `recall_score`,
`services/srs.py::rolling_accuracy`), each updated only on an "informative" attempt for that
dimension — not every answer moves both:
- `application_score` — updated only when the served question's `source == "ai_generated"`
  (a genuinely fresh, novel sentence) as opposed to `source == "seed"` (the one fixed,
  drillable sentence per grammar item the learner might just pattern-match against). Answering
  a seed question leaves it untouched.
- `discrimination_score` — updated only when the served question had
  `has_confusion_distractor == true` (at least one of its 3 distractors was drawn from a real
  `commonly_confused`/`similar_form` `grammar_relation` edge rather than the uniform-random
  fallback pool) — getting it wrong then plausibly means confusing this item with a real
  confusable partner. Answering a question with no confusion-derived distractor leaves it
  untouched.
- Both default to **0.5** (not 0.0) on a fresh `grammar_progress` row, and stay at 0.5 until
  their first informative attempt lands — this is a deliberate "no signal yet" neutral
  baseline, distinct from a confirmed-bad 0.0. In particular, without an `OPENAI_API_KEY`/
  `ANTHROPIC_API_KEY` configured (no AI-generated questions ever served), `application_score`
  stays at 0.5 for every item indefinitely — this is expected, not a bug.
Request body:
```
AnswerRequest = {
  question_id: string (uuid),
  selected_option: string,        # "A".."D"
  response_time_ms?: number,
}
```
Response 200:
```
AnswerResponse = {
  is_correct: boolean,
  correct_option: string,          # "A".."D"
  explanation_ru: string | null,   # contrastive explanation, Russian
  sentence_full_html: string,      # full sentence with target revealed, for post-answer display
  next_review: string (ISO datetime),   # updated SRS due date for this grammar item
}
```
Response 404: `{"detail": "Question not found"}`
Response 500: grammar/progress record missing (should not happen — data integrity error)

### POST /production/session
Offline sentence-production prompts (no LLM call, no database writes).
Request body: `{ size?: 5 | 10 | 20 (default 5), level?: "N5" | "N4" | "N3" | "N2" | "N1" }`
Response 200: `{ prompts: [{ grammar_id, level, pattern_hint, meaning_hint, meaning_ru, formation_hints[] }] }`
— overdue items first, topped up with random ones. The target form is NOT included.

### POST /production/check
Advisory check of a learner-typed Japanese sentence; never changes grammar_progress.
Request body: `{ grammar_id: uuid, answer: string (max 500 chars) }`
Response 200: `{ match: "exact" | "stem" | "none" | "empty", too_short, target_construction,
model_sentence_html, model_sentence_clean }`
Response 404: unknown grammar_id.

### GET /stats
Dashboard aggregates for the single owner.
Query params (optional):
```
level   - V4, NEW. Same semantics as GET /grammar's `level`: "N3"|"N4"|"N2". Omitted =
          combined stats across all levels (unchanged pre-V4 behavior). Scopes every count
          below to that level's grammar_progress rows only. [ADR-23] Chosen over a separate
          `/stats/by-level` endpoint — for a personal tool at this data volume (<=500 rows
          total), 3 parallel `GET /stats?level=X` calls are cheap enough for a per-level
          breakdown.
```
Response 200:
```
StatsOut = {
  due_count: number,
  new_count: number,
  learning_count: number,
  review_count: number,
  mastered_count: number,
  recall_pct: number,          # rolling accuracy, 0..1
  application_avg: number,     # avg grammar_progress.application_score across matched rows,
                                # 0..1, neutral 0.5 per row until it has an informative
                                # (ai_generated-question) attempt — see POST /review/answer
  discrimination_avg: number,  # avg grammar_progress.discrimination_score, same semantics,
                                # neutral 0.5 per row until it has a confusion-distractor attempt
  total_items: number,         # V4, NEW. Count of grammar rows matching `level` (or all
                                # levels combined if omitted). Replaces any client-side
                                # hardcoded item-count constant.
}
```

### GET /llms.txt
This file.

## Notes for LLM agents

- No authentication on any endpoint — this is a personal, local/self-hosted tool, not a
  multi-tenant service. Do not add credentials.
- `POST /review/session` has side effects (schedules background generation); safe to call
  repeatedly, but each call may enqueue new AI generation work if a provider key is set.
- AI-generated example sentences require `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` (selected via
  `LLM_PROVIDER`); without either, only the ~200 seeded questions are ever served.
- `grammar_relation` edges (V2) are populated by a manual, owner-gated script
  (`uv run python -m app.scripts.generate_relations`), never on any request path. Without an
  LLM key configured it still produces useful `source="heuristic"` edges (shared
  function-word stem / meaning-keyword overlap / shared-kanji scoring); with a key, re-running
  it upgrades those to `source="llm_classified"` with a real relation_type + confidence.
- Vocabulary (V3) is seeded once from a repo-local JSON snapshot of the owner's personal N3
  word/kanji lists (`uv run python -m app.scripts.seed_vocabulary`), not from any request path.
  `POST /review/answer` records per-word correct/incorrect exposure (whole-question
  correctness attributed to every matched word — no per-word signal exists) against
  `user_vocabulary`; a word counts as "known" after enough consecutive correct exposures
  (see ARCHITECTURE.md ADR-15/19), at which point it's included in `known_words`.
- `confusion`/`weak_points` session modes and confusion-biased distractor/generation selection
  (V3) both read from `grammar_relation` — they degrade gracefully (fewer/no results, uniform
  random distractors) when that table is empty, they never error.
- N4/N2 grammar content (V4) is seeded once from repo-local, DB-ready JSON
  (`data/seed/n4_grammar_authored.json`, `data/seed/n2_grammar_authored.json`) via
  `uv run python -m app.scripts.seed_import_authored`, never from any request path. Upserts by
  a deterministic `source_note_id` hashed from `(level, key)` (ADR-21) — idempotent re-run on
  an edited file updates the same rows without touching their `grammar_progress`/SRS state.
  Never reads or modifies N3's `n3_grammar_anki_export.json`-sourced rows.
- Curated relation edges (V4) are seeded once from repo-local JSON
  (`data/seed/relations_curated_*.json`, glob) via
  `uv run python -m app.scripts.import_curated_relations`, never from any request path. A
  curated (`source="manual"`) edge supersedes both `heuristic` and `llm_classified` rows for
  the exact same unordered pair it covers (ADR-22); pairs it doesn't cover keep whatever edge
  they already had. `--purge-remaining-heuristic` optionally deletes every remaining
  `source="heuristic"` row after curated pairs are processed (off by default).
"""
