# ТЗ: Japanese Grammar Retrieval Trainer

Status: draft v1 · Owner: champ59ru · Scope: personal tool (single-user, no auth/payments)

## 1. Цель и гипотеза

См. исходную идею: [japanese_grammar_retrieval_trainer (1).md](./japanese_grammar_retrieval_trainer%20%281%29.md).

Гипотеза продукта (§69 исходника): пассивное знание грамматики JLPT сильно опережает
активное применение. Регулярный spaced retrieval в новых контекстах + contrastive
questions между похожими конструкциями значительно повышают active recall и discrimination.

MVP должен проверить именно этот loop, не более.

## 2. Решённые вопросы (ответы владельца, 2026-09-22)

| Вопрос | Решение |
|---|---|
| Аудитория | Personal tool. Один пользователь (владелец). Без auth, без payments, без multi-tenant. |
| Контент N3 grammar | Уже есть готовая curated колода **"N3 Grammar" (Anki, 205 карточек)** — expression, reading, meaning (RU), pattern, formation/connection, example sentence с ruby-furigana. Экспортирована → [data/seed/n3_grammar_anki_export.json](./data/seed/n3_grammar_anki_export.json). Это основной seed для Grammar DB, НЕ OCR из PDF (дорого по токенам, ниже качество). |
| LLM provider | Dual-provider: OpenAI И Anthropic, с ручным/конфигурируемым переключением (то один дешевле, то другой). Provider-agnostic abstraction layer обязателен. |
| Платформа MVP | Web app / PWA, Next.js. Mobile (Expo) — не раньше V2. |

## 3. Источники данных, уже доступные локально

Рабочая директория с материалами: `E:\Main\Main\Папки\Japanese` (доп. working dir).

- **`Анки/колоды которые нужно сравнить/N3 Grammar.apkg`** — 205 note, notetype "N3 Grammar+".
  Поля: `Expression` (html+ruby+bold на целевую конструкцию), `Reading` (кана, с bold),
  `Meaning` (перевод RU), `Pattern` (формулировка правила + значение RU),
  `Connection` (formation-таблица: как констр. крепится к гл./прил./сущ. с примерами),
  `ExpressionClean` (то же предложение без ruby/bold — plain JP).
  → уже экспортировано в JSON, лежит в `data/seed/`.
- `JLPT SENSEI/N3/` + `JLPT N3 Grammar List Flashcards Set.zip` — резервный/сверочный источник
  (не основной, использовать только для gap-filling, если в личной колоде чего-то не хватает).
- `Анки/кандзи н3/*.csv`, `Анки/слова н3/*.csv` — N3 vocabulary/kanji, пригодится для
  vocabulary-tracking (adaptive furigana, §21-23 идеи) в V2.
- `E:\Main\Dev\WebApps\JP Grammar app\... Anki/` (jpvocab, отдельный существующий python-проект,
  не трогаем/не смешиваем) — просто referenced как пример работы с JMdict/Kanjium/Tatoeba,
  can reuse approach for vocabulary lookups later.
- Kanzen Master PDF (N3/N4/N2, десятки–сотни МБ сканов) — **не парсим**, слишком дорого и
  неточно через LLM-vision/OCR. Используем только личную Anki-колоду как источник истины
  для MVP grammar list; PDF остаётся у юзера как источник для доп. ручной сверки при желании.

## 4. Границы MVP (что строим сейчас)

Только фичи Tier 1 + минимально необходимые куски Tier 2 (см. §68 идеи), под personal-use:

1. **Grammar Database** — 205 N3 конструкций, seeded из Anki-экспорта, структурировано
   (expression, reading, meaning, formation rules per part-of-speech, example sentence, tags).
2. **Lesson/Curriculum structure** — т.к. личной колоды нет привязки к урокам Shin Kanzen,
   на MVP curriculum = плоский список "All N3 Grammar" (см. §24 идеи, curriculum variant
   "All N3 Grammar"). Группировка по Anki tags, если они несут смысл (проверить при экспорте).
3. **4-choice questions** — fill-in-the-blank на основе example sentence из колоды +
   3 дистрактора. MVP дистракторы: другие grammar items (сначала — случайные similar по
   тегам/эвристике; AI-generated contrastive distractors — Tier 3, после базового loop).
4. **SRS** — per-grammar-item state (first_seen, next_review, interval, ease, repetitions),
   базовый алгоритм на фиксированных интервалах (§6 идеи: 0/1/3/7/14/30/60/120 дней),
   error → сократить интервал; adaptive-alg — V2.
5. **New AI-generated examples** — LLM генерирует новые предложения для уже изученной
   грамматики (не переиспользует одно и то же предложение бесконечно), через
   dual-provider abstraction (OpenAI/Anthropic), с validation layer (§32 идеи, упрощённо
   для MVP: grammar-fit check + duplicate check).
6. **Furigana** — MVP: `By JLPT level` режим (§21), toggle Always/Never/By-level.
   Adaptive per-word (§22) — V2 (требует UserVocabulary tracking).
7. **Basic statistics / dashboard** — due count, recall %, mastered/learning/weak counts,
   как в §27 идеи, упрощённо (без разбивки по lessons, т.к. lessons нет в MVP).
8. **Review session UX** — question → answer → immediate feedback + contrastive explanation
   → next (§41-42 идеи). Session length: 5/10/20 вопросов.

### Явно вне MVP (V2+, см. §60-63 идеи)

Grammar Graph (explicit relations/confusion sets), Adaptive Furigana, adaptive difficulty
algorithm, weak-point-driven personalized generation, vocabulary tracking, lesson-based
curriculum (Shin Kanzen lesson numbers), N5–N1 multi-level, custom grammar input, Anki
import UI, sentence production mode, speaking mode, multi-user/auth/payments.

## 5. Данные / основные сущности (Postgres)

Урезано от §53 идеи под personal MVP (без `User` multi-tenant — один системный пользователь
или вообще без явной таблицы User на MVP, hardcoded owner):

```
Grammar          — id, expression, expression_clean, reading, meaning_ru, pattern_text,
                    formation_rules (jsonb: по частям речи), level(N3), tags[], source_note_id
GrammarProgress   — grammar_id, status(new/learning/review/mastered), first_seen, last_reviewed,
                    next_review, ease, interval_days, repetitions,
                    recall_score, application_score, discrimination_score
Question          — id, grammar_id, question_type, sentence_with_blank, options(jsonb: A-D),
                    correct_option, source(seed|ai_generated), generation_model,
                    generation_prompt_version, validation_status, created_at
QuestionAttempt   — id, question_id, grammar_id, selected_option, correct_option, is_correct,
                    response_time_ms, error_type, created_at
```

`GrammarRelation`, `Vocabulary`, `UserVocabulary`, `Curriculum`, `Lesson` — модели остаются в
дизайне (см. идею §9-10, §53-54), но таблицы/логика — с V2, когда появится Grammar Graph и
vocabulary tracking.

## 6. AI generation pipeline (MVP, упрощённо от §8/§31/§57 идеи)

```
Trigger: юзер начинает review сессию И для грамматики < N доступных
неиспользованных вопросов (N настраиваемый, дефолт 5)
        ↓
Background job генерирует batch (10-20 sentences) для этой грамматики
        ↓
Provider abstraction: OpenAI | Anthropic (конфиг в .env, переключаемо)
        ↓
Validation (упрощённо на MVP): grammar-target действительно нужен по смыслу,
не дубликат ранее сгенерированного (embedding или строгое string-similarity),
не более N% случаев ambiguous (эвристика/second LLM-pass опционально)
        ↓
Сохранить в Question table (source=ai_generated), validation_status
        ↓
Serve later — не генерировать вопрос в момент клика
```

Дистракторы на MVP: 3 случайных других N3-grammar item (расширить в V2 через grammar graph
similarity/tags). Провалидировать, что дистрактор грамматически может стоять в той же
позиции (несложная эвристика, не blocking для MVP).

## 7. Стек

- Frontend: Next.js (App Router) + TypeScript + Tailwind, отдаём как PWA.
- Backend: Python + FastAPI + PostgreSQL (см. `rules-main/` — uv, typed, beartype).
- AI: provider-agnostic layer, OpenAI + Anthropic adapters, конфиг переключения в env/settings UI.
- Infra на MVP: без Redis/воркеров отдельно — background generation можно на FastAPI
  BackgroundTasks/простом cron-скрипте; upgrade до Redis+worker при реальной нагрузке.
- Hosting: Vercel (frontend) + Supabase (Postgres) — доступны MCP-инструменты в этой сессии.
- Auth: НЕТ на MVP (personal tool). Если понадобится позже — Google OAuth+JWT по `auth.md`.

## 8. Критерий готовности MVP

Повторяет user flow §59 идеи, без Sign up/lesson-selection (нет lessons на MVP):

```
Открыть app → Dashboard (due count) → Start Review → 4-choice question
(seed или AI-generated sentence) → Answer → Contrastive explanation → SRS
пересчитывает next_review → назад в Dashboard, счётчики обновились
```

Плюс: все 205 N3 grammar items загружены и доступны для review с первого запуска.

## 9. Открытые риски / что проверить по ходу

- Качество AI-дистракторов без grammar graph может быть слабым первое время — ок для MVP,
  первый V2-таргет.
- Anki tags в колоде могут быть пустыми/несистемными — проверить при импорте, при
  необходимости сгруппировать вручную/через LLM classification в grammar categories
  (§46 идеи: Conditionals/Causality/Contrast/...).
- Dual LLM provider — нужны оба API key в .env; если только один под рукой на старте,
  архитектура должна работать с одним и молча не звать другой.
