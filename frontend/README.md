# frontend

Next.js (App Router) + TypeScript + Tailwind PWA frontend for the Japanese N3 Grammar
Retrieval Trainer. See `../ARCHITECTURE.md` for the full system design.

## Setup

```bash
npm install
cp .env.example .env.local   # set NEXT_PUBLIC_API_BASE_URL once backend is running/deployed
npm run dev
```

## Status

Scaffolded by the architect agent: App Router shell (Dashboard/Review/Stats routes), typed
API client (`src/lib/api.ts`) against the documented backend contract (`ARCHITECTURE.md`
§8), PWA manifest + icons, and `FuriganaText.tsx` — the Always/Never/By-level furigana
renderer (ARCHITECTURE.md §5) — fully implemented since it's a pure function with no backend
dependency. `QuestionCard`/`ContrastiveExplanation`/`DueCounter` are presentational
components; the pages themselves are static shells with `TODO` comments pointing at
`ARCHITECTURE.md` §9 Phase 4 tasks 4.2-4.6 (data fetching, session flow, PWA service worker
registration, furigana-mode persistence) — that's the next slice for frontend-dev.
