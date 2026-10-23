# Plan — finish roadmap (branch feature/finish-roadmap)

- [x] T1 Family-scoped confusion practice. Backend: `family_member_ids` + `select_confusion_progress(family_of=)`, `SessionRequest.family_of` (confusion mode only, else 422). Frontend: cluster card links `/review?mode=confusion&family=<id>`; review page passes `family_of`. Check: pytest, mypy, tsc.
- [x] T2 Sentence-production practice (offline). Prompt = pattern + Russian translation of a seeded example; learner types Japanese; advisory string check (exact / conjugation-stem / none) + model sentence; self-rating client-side only. Speaking (audio/ASR) deliberately out of scope: needs a browser speech API or paid service, listed under Needs owner.
- [x] T3 LLM relation re-classification behind `LLM_RELATION_RECLASSIFY` flag (`python -m app.scripts.generate_relations --reclassify`): only `source=heuristic` edges are re-sent; curated/manual edges untouched; provider error = no writes. Mocked tests only.
- [x] T4 N5/N1 scaffold: validator + empty seed slots + format docs. Sample content explicitly deferred: N5/N1 grammar cannot be derived from the N4/N3/N2 seed data and must not be invented.
- [ ] T5 Docs (README roadmap, llms.txt), final full verification.

## Needs owner
- Speaking practice (voice input/ASR or TTS): not built; needs a decision on browser Web Speech API vs a paid service.
- Production practice results are not persisted into SRS by design (stateless). Say if you want them to feed a separate score.
- Set `LLM_RELATION_RECLASSIFY=true` plus an API key, then run `uv run python -m app.scripts.generate_relations --reclassify` once, to verify T3 live and review the report (costs tokens; heuristic edges that the model rejects are deleted).
- N5 / N1 content: provide a source (deck/textbook) or authorize authoring; then fill `data/seed/n5|n1_grammar_authored.json`, validate, import, and enable the level in `LevelSelector.tsx` / `GrammarLevel`.
- Restart backend + frontend after merging (new routes `/production/*`, `family_of`).
