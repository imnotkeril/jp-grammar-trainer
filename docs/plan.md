# Plan — finish roadmap (branch feature/finish-roadmap)

- [x] T1 Family-scoped confusion practice. Backend: `family_member_ids` + `select_confusion_progress(family_of=)`, `SessionRequest.family_of` (confusion mode only, else 422). Frontend: cluster card links `/review?mode=confusion&family=<id>`; review page passes `family_of`. Check: pytest, mypy, tsc.
- [x] T2 Sentence-production practice (offline). Prompt = pattern + Russian translation of a seeded example; learner types Japanese; advisory string check (exact / conjugation-stem / none) + model sentence; self-rating client-side only. Speaking (audio/ASR) deliberately out of scope: needs a browser speech API or paid service, listed under Needs owner.
- [ ] T3 LLM relation re-classification behind `LLM_RELATION_RECLASSIFY` flag, mocked tests.
- [ ] T4 N5/N1 scaffold: importer/seed format + sample or explicit deferral.
- [ ] T5 Docs (README roadmap, llms.txt), final full verification.

## Needs owner
- Speaking practice (voice input/ASR or TTS): not built; needs a decision on browser Web Speech API vs a paid service.
- Production practice results are not persisted into SRS by design (stateless). Say if you want them to feed a separate score.
