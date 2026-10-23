# Plan — finish roadmap (branch feature/finish-roadmap)

- [x] T1 Family-scoped confusion practice. Backend: `family_member_ids` + `select_confusion_progress(family_of=)`, `SessionRequest.family_of` (confusion mode only, else 422). Frontend: cluster card links `/review?mode=confusion&family=<id>`; review page passes `family_of`. Check: pytest, mypy, tsc.
- [ ] T2 Sentence-production practice (offline): see design in ARCHITECTURE-free note below.
- [ ] T3 LLM relation re-classification behind `LLM_RELATION_RECLASSIFY` flag, mocked tests.
- [ ] T4 N5/N1 scaffold: importer/seed format + sample or explicit deferral.
- [ ] T5 Docs (README roadmap, llms.txt), final full verification.

## Needs owner
(filled as tasks complete)
