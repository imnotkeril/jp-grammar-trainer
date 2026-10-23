# Seed data

| File | What | Imported by |
|---|---|---|
| `n3_grammar_anki_export.json` | 205 N3 items exported from the owner's Anki deck | `app.scripts.seed_import` |
| `n4_grammar_authored.json`, `n2_grammar_authored.json` | authored N4 / N2 items (DB-ready) | `app.scripts.seed_import_authored` |
| `n5_grammar_authored.json`, `n1_grammar_authored.json` | **empty scaffolds** — no content yet (see below) | `app.scripts.seed_import_authored` (imports 0 rows) |
| `relations_curated_*.json` | hand-curated relation edges | `app.scripts.import_curated_relations` |
| `vocabulary_n3.json` | N3 words/kanji for adaptive furigana | `app.scripts.seed_vocabulary` |

## Authored file format

```json
{
  "level": "N5",
  "items": [
    {
      "key": "n5_001_desu",
      "expression_html": "<ruby>私<rt>わたし</rt></ruby>は<ruby>学生<rt>がくせい</rt></ruby><b>です</b>。",
      "reading": "わたしは がくせい<b>です</b>。",
      "meaning_ru": "Я студент.",
      "pattern_text": "Паттерн: 名詞 + です\nЗначение: вежливое утверждение",
      "formation_rules": [{"pos": "名詞", "form_label": "名詞＋です", "example_html": "学生<b>です</b>"}],
      "target_construction": "です",
      "tags": ["N5", "copula"]
    }
  ]
}
```

- `key`: lowercase, starts with the level (`n5_`), unique and **never renamed** after first import (the row id is derived from `level:key`).
- `expression_html`: one example sentence, furigana as `<ruby>…<rt>…</rt></ruby>`, the tested construction wrapped in `<b>`.
- `target_construction` must be the plain text of that `<b>` span.
- `meaning_ru` is the Russian translation of the example sentence; `pattern_text` uses the `Паттерн: … / Значение: …` two-line convention (used by the sentence-production hints).

## Adding N5 / N1

1. Author items into `n5_grammar_authored.json` / `n1_grammar_authored.json` from a source you can vouch for (textbook, Anki deck) — the importer cannot make content up, and neither should a script.
2. Check offline: `cd backend && uv run python -m app.scripts.validate_authored_seed`
3. Import: `uv run python -m app.scripts.seed_import_authored` (idempotent).
4. Enable the level in the UI: `frontend/src/components/LevelSelector.tsx` and `GrammarLevel` in `frontend/src/lib/types.ts`. The backend already accepts all five levels.
