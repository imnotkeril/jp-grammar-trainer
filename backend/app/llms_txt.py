from __future__ import annotations

"""Static content for GET /llms.txt.

Kept as a plain string (not a file read from disk) so it ships inside the app package
regardless of working directory / deploy target. Update this whenever a route or schema
in app/routers/* or app/schemas/* changes — it must stay in sync with the real API surface.
"""

LLMS_TXT = """\
# JP Grammar Trainer API

> Personal, single-user Japanese N3 grammar spaced-retrieval trainer backend. No auth —
> every row belongs to the single owner. FastAPI + PostgreSQL. See /ARCHITECTURE.md in the
> project repo for full system design, DB schema, SRS algorithm, and AI generation pipeline.

Base URL: this server's origin (e.g. http://localhost:8000 in dev). All endpoints return JSON
except this file. CORS is restricted to the origins in CORS_ALLOWED_ORIGINS.

## Endpoints

### GET /health
Liveness check.
Response 200: `{"status": "ok"}`

### GET /grammar
List all seeded N3 grammar items, ordered by original Anki note id.
Response 200: `GrammarOut[]`

```
GrammarOut = {
  id: string (uuid),
  expression_html: string,       # original <ruby>/<rt>/<b> markup, target construction bolded
  expression_clean: string,      # plain Japanese, no markup
  reading: string,                # kana reading
  meaning_ru: string,             # Russian translation
  pattern_text: string,           # rule statement + meaning
  formation_rules: FormationRule[],
  level: string,                  # "N3" for all rows on MVP
  tags: string[],                 # empty on MVP (source deck has no tags)
  target_construction: string,    # plain text of the grammar point being tested
}
FormationRule = { pos: string, form_label: string, example_html: string }
```

### GET /grammar/{grammar_id}
Single grammar item by id.
Path param: `grammar_id` (uuid)
Response 200: `GrammarOut` (see above)
Response 404: `{"detail": "Grammar item not found"}`

### POST /review/session
Start a review session: selects due items (overdue first, then new), serves one question per
item, and fires background AI-generation for any item running low on unused questions
(silently skipped if no LLM API key is configured — seed questions still serve).
Request body:
```
SessionRequest = { size?: 5 | 10 | 20 }   # default 10
```
Response 200:
```
SessionResponse = { questions: QuestionOut[] }
QuestionOut = {
  id: string (uuid),
  grammar_id: string (uuid),
  sentence_with_blank_html: string,   # ruby-preserving sentence with target replaced by ___
  options: QuestionOption[],           # always 4, one correct + 3 distractors, pre-shuffled
}
QuestionOption = { key: string, text: string }   # key is "A".."D"
```
Note: an item with no valid question yet available (generation not landed) is skipped for
this round and stays due for the next session — the response may contain fewer items than
`size`.

### POST /review/answer
Submit an answer to a served question. Records the attempt, runs the SRS scheduler to update
that grammar item's progress, and returns a contrastive explanation.
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

### GET /stats
Dashboard aggregates for the single owner.
Response 200:
```
StatsOut = {
  due_count: number,
  new_count: number,
  learning_count: number,
  review_count: number,
  mastered_count: number,
  recall_pct: number,          # rolling accuracy, 0..1
  application_avg: number,     # placeholder, V2
  discrimination_avg: number,  # placeholder, V2
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
"""
