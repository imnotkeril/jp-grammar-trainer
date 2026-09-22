# Japanese Grammar Retrieval Trainer

## 1. Концепция

Приложение для изучения японской грамматики, построенное вокруг **active retrieval + spaced repetition + contrastive practice**.

Основная проблема:

> Пользователь проходит урок Shin Kanzen Master, понимает новую грамматику, делает упражнения и тест. Затем грамматика практически исчезает из активной практики. Через несколько уроков она может встретиться один раз в общем тесте, но этого недостаточно для формирования устойчивого recall и автоматического выбора конструкции в реальной речи.

Приложение закрывает именно этот пробел.

Оно не обязано заменять Shin Kanzen Master. Учебник остаётся источником структурированного обучения, а приложение становится постоянным слоем **активного повторения и применения**.

Основная идея:

```text
Shin Kanzen Master / другой курс
                ↓
          Изучение урока
                ↓
       Отметка грамматики
                ↓
      Spaced Repetition
                ↓
     Новые контексты и тесты
                ↓
   Ошибки / слабые различия
                ↓
 Adaptive Review / повторение
```

---

# 2. Главная проблема

Обычный процесс выглядит примерно так:

```text
Lesson 7
↓
объяснение
↓
примеры
↓
упражнения
↓
тест
↓
Lesson 8
↓
Lesson 9
↓
Lesson 10
...
↓
общий тест
```

Проблема заключается в том, что между изучением и следующим meaningful retrieval может пройти слишком много времени.

Кроме того, простое повторное чтение одного и того же примера малоэффективно.

Например:

> 日本人だからといって、みんなが納豆を好きなわけではない。

Если пользователь прочитал это предложение 15 раз, он может прекрасно узнавать его, но это не означает, что он сможет самостоятельно выбрать `わけではない` в новом контексте.

Поэтому приложение должно тренировать не recognition, а:

1. Recognition — узнавание конструкции.
2. Recall — вспоминание значения/формы.
3. Application — применение в новом контексте.
4. Discrimination — различение похожих конструкций.

Главная цель — переход от:

> «Я это где-то видел»

к:

> «Я автоматически понимаю, что здесь нужна именно эта конструкция».

---

# 3. Позиционирование

Не:

> Anki с японской грамматикой.

Лучше:

> Adaptive Japanese Grammar Retrieval Trainer

или:

> Spaced repetition for Japanese grammar with AI-generated contextual practice.

Ключевой USP:

**Приложение не просто повторяет грамматику. Оно регулярно заставляет пользователя выбирать и применять её в новых контекстах, включая специально подобранные похожие грамматические конструкции.**

---

# 4. Целевая аудитория

Основная:

- изучающие японский примерно N5–N1;
- пользователи Shin Kanzen Master;
- пользователи других JLPT textbooks;
- люди, которые понимают грамматику пассивно, но забывают её в реальном использовании;
- пользователи Anki, которым неудобно самостоятельно создавать большое количество качественных grammar cards.

Особенно сильный use case:

> Пользователь учит N3/N2 по Shin Kanzen Master и хочет автоматически поддерживать всю пройденную грамматику.

---

# 5. Основной пользовательский сценарий

## 5.1. Пользователь изучает урок

Например:

```text
N3 Shin Kanzen Master
Lesson 7
```

В уроке изучаются:

```text
〜わけではない
〜とは限らない
〜に違いない
...
```

Пользователь проходит материал и тест.

После этого нажимает:

> Complete Lesson

Приложение добавляет соответствующую грамматику в review queue.

---

# 6. Spaced Repetition

Каждая grammar item получает собственное состояние.

Пример:

```text
〜わけではない

First learned:
19 Sep

Next review:
20 Sep

Retention:
72%

Application:
61%

Discrimination:
44%
```

Базовый scheduler может использовать интервалы:

```text
Day 0
Day 1
Day 3
Day 7
Day 14
Day 30
Day 60
Day 120
```

Но в дальнейшем алгоритм должен быть адаптивным.

Ошибка:

```text
interval ↓
difficulty ↑
```

Уверенный правильный ответ:

```text
interval ↑
difficulty ↓
```

Повторение не должно быть одинаковым для всех конструкций.

---

# 7. Важнейший принцип: новые предложения

Одна и та же грамматика не должна постоянно появляться в одном и том же sentence.

Например:

### Review 1

> 彼は日本語が話せるからといって、漢字も読める＿＿＿＿。

### Review 2

> 高級なレストランだからといって、必ずしも料理がおいしい＿＿＿＿。

### Review 3

> 彼女は英語が得意だが、海外で働きたい＿＿＿＿。

Контексты меняются.

Пользователь должен извлекать грамматику из памяти, а не узнавать конкретное предложение.

---

# 8. AI-generated examples

AI может генерировать новые предложения для уже изученной грамматики.

Однако AI не должен быть единственным источником истины.

Pipeline:

```text
Grammar Database
       ↓
Prompt / constraints
       ↓
LLM generation
       ↓
Validation
       ↓
Question Database
       ↓
User
```

Генерация должна учитывать:

- grammar;
- JLPT level;
- vocabulary difficulty;
- register;
- context;
- similar grammar;
- known user mistakes;
- previously generated sentences.

---

# 9. Grammar Database

Грамматика должна храниться не как простая карточка, а как структурированный объект.

Пример:

```text
Grammar ID:
n3_wake_dewa_nai

Expression:
〜わけではない

Level:
N3

Meaning:
не то чтобы...
не обязательно...
дело не в том, что...

Formation:
Verb plain form + わけではない
い-adjective + わけではない
な-adjective + なわけではない
Noun + というわけではない

Functions:
- partial negation
- correction of assumption
- denying an overgeneralization

Register:
neutral / written / spoken

Similar:
〜とは限らない
〜わけがない
〜というわけではない

Related:
〜わけだ

Common mistakes:
...

Prerequisites:
...

Examples:
...
```

---

# 10. Grammar Graph

Это одна из главных особенностей продукта.

Грамматика должна иметь связи с другими конструкциями.

Например:

```text
                    わけだ
                      │
          ┌───────────┼────────────┐
          ↓           ↓            ↓
   わけではない    わけがない   わけにはいかない
          │
          ↕
    とは限らない
```

Каждая связь может иметь тип:

```text
similar_meaning
similar_form
commonly_confused
opposite
prerequisite
advanced_version
related
```

Это позволяет создавать осмысленные distractors.

---

# 11. Contrastive Learning

Обычный тест:

> Какую грамматику нужно использовать?

Четыре случайных ответа.

Это недостаточно эффективно.

Вместо этого система должна знать:

> `わけではない` часто путают с `とは限らない`.

И создавать тест:

```text
A. わけではない
B. とは限らない
C. わけがない
D. に違いない
```

То есть все варианты должны быть правдоподобными.

Пользователь вынужден понимать **почему** подходит одна конструкция и **почему** остальные не подходят.

---

# 12. Четыре варианта ответа

Основной формат теста:

**single-choice, 4 options.**

Например:

> 日本に10年住んでいるからといって、日本の文化を全部知っている＿＿＿＿。

A. わけではない  
B. わけがない  
C. とは限らない  
D. に違いない

Всегда:

- 4 варианта;
- один правильный;
- варианты A/B/C/D;
- distractors должны быть грамматически и семантически правдоподобными;
- желательно выбирать distractors из связанных grammar nodes.

Не нужно делать варианты очевидно неправильными.

---

# 13. Типы вопросов

## 13.1. Fill in the blank

> この店は高いからといって、料理がおいしい＿＿＿＿。

A. わけではない
B. ...

Это базовый тип.

---

## 13.2. Grammar selection

Дано предложение с пустым местом.

Пользователь выбирает правильную конструкцию.

---

## 13.3. Meaning discrimination

Даны несколько грамматик, нужно выбрать ту, которая соответствует смыслу.

---

## 13.4. Context discrimination

Контекст длиннее.

Пользователь должен понять ситуацию, а не только грамматический шаблон.

---

## 13.5. Error correction

Пользователь видит предложение:

> 日本人だからといって、全員が寿司が好きとは限らない。

И выбирает, нужна ли другая конструкция или предложение корректно.

---

## 13.6. Translation-based question

Например:

> «Не то чтобы я не хотел идти, просто у меня нет времени».

Выбрать правильную японскую конструкцию.

Такой режим желательно использовать ограниченно, поскольку перевод может создавать дополнительную неоднозначность.

---

# 14. Explanation после ответа

После каждого вопроса приложение показывает:

1. правильный ответ;
2. значение конструкции;
3. почему она подходит;
4. почему похожие варианты не подходят.

Например:

```text
〜わけではない
= не то чтобы / не обязательно

Используется для частичного отрицания
или отрицания предположения.

とは限らない
= не обязательно / не всегда

Разница:
わけではない → отрицается конкретное предположение
とは限らない → утверждается, что результат не гарантирован
```

То есть объяснение должно быть **contrastive**, а не просто dictionary definition.

---

# 15. Confusion Sets

Для каждой грамматики можно создать набор конструкций, которые особенно часто путаются.

Пример:

```text
〜わけではない
〜とは限らない
〜わけがない
〜ことはない
```

Система может создавать специальный режим:

> Confusion Practice

И давать 10–20 вопросов исключительно на эти конструкции.

Это особенно полезно для N3/N2/N1, где проблема часто уже не в том, что пользователь не знает значение, а в том, что несколько конструкций кажутся взаимозаменяемыми.

---

# 16. Тесты по пройденному материалу

Пользователь может выбрать:

```text
Level:
N3

Lessons:
1–10

Questions:
10 / 20 / 30 / 50

Mode:
Mixed
```

И получить тест только по пройденной грамматике.

---

# 17. Количество предложений на одну грамматику

Нужна отдельная настройка.

Например:

```text
Questions per grammar:

1
2
3
5
10
```

Пользователь выбирает:

> 3 sentences per grammar

Если выбраны:

```text
20 grammar points
×
3 questions
=
60 questions
```

Затем они перемешиваются.

---

# 18. Shuffle

В тесте не должно быть:

```text
わけではない × 5
とは限らない × 5
わけがない × 5
```

если пользователь не включил focused practice.

По умолчанию:

```text
G1
G8
G3
G17
G2
G11
...
```

Это заставляет пользователя заново определять, какую конструкцию применять.

---

# 19. Режимы тестирования

## Quick Review

```text
5 / 10 / 20 questions
```

## Due Review

Только грамматика, которую нужно повторить сейчас.

## Mixed Review

Вся изученная грамматика.

## Weak Points

Грамматика с низким retention.

## Confusion Practice

Только похожие конструкции.

## Lesson Test

Тест конкретного урока.

## Range Test

Например:

```text
N3 Lesson 1–10
```

## Full Level Test

Например:

```text
All learned N3 grammar
```

---

# 20. Furigana

Фуригана должна быть полноценной частью системы.

Главная проблема:

Если включить furigana на всё:

> 日本（にほん）の経済（けいざい）について...

текст становится перегруженным.

Если отключить всё:

> 環境問題について議論する。

пользователь может застревать на vocabulary, а не тренировать grammar.

Поэтому нужен adaptive system.

---

# 21. Furigana settings

Например:

```text
Furigana

○ Always
○ Never
● By JLPT level
○ Adaptive
```

При `By JLPT level`:

```text
Show furigana for:
N3+
```

Тогда:

```text
N5 vocabulary → no furigana
N4 vocabulary → no furigana
N3 vocabulary → furigana
N2 vocabulary → furigana
N1 vocabulary → furigana
```

---

# 22. Adaptive Furigana

Более продвинутая система.

JLPT level используется как baseline.

Но приложение отслеживает индивидуальное знание слова.

Например:

```text
環境
N3

User:
correct reading × 12

→ considered known
→ furigana hidden
```

А:

```text
政策
N2

User:
reading errors × 3

→ keep furigana
```

Таким образом:

```text
JLPT level
+
personal vocabulary retention
=
actual furigana display
```

Это гораздо лучше фиксированного уровня.

---

# 23. Furigana должна работать отдельно от grammar level

Например пользователь проходит N3 grammar, но в предложении встречается N2 vocabulary.

Grammar:

```text
N3
```

Vocabulary:

```text
N2
```

Furigana:

```text
政策（せいさく）
```

То есть уровень grammar и уровень vocabulary — отдельные metadata.

---

# 24. Lessons

Приложение должно иметь собственную curriculum structure.

Например:

```text
N3
├── Lesson 01
├── Lesson 02
├── Lesson 03
...
└── Lesson 20

N2
├── Lesson 01
...
```

Но curriculum желательно делать независимым от одного учебника.

Например:

```text
Curriculum
├── Shin Kanzen Master N3
├── Shin Kanzen Master N2
├── Custom
└── All N3 Grammar
```

---

# 25. Shin Kanzen Master как основной use case

Приложение может предоставить структуру:

```text
Shin Kanzen Master N3 Grammar

Lesson 1
  Grammar A
  Grammar B
  Grammar C

Lesson 2
  Grammar D
  Grammar E
...
```

Пользователь завершает урок:

> Complete

И приложение автоматически запускает SRS.

В идеале пользователь вообще не должен вручную создавать Anki cards.

---

# 26. Onboarding

Первый запуск:

```text
What are you studying?

○ Shin Kanzen Master N3
○ Shin Kanzen Master N2
○ Other
○ Custom grammar
```

Затем:

```text
Already completed:

☐ Lesson 1
☐ Lesson 2
☐ Lesson 3
...
```

Приложение создаёт initial review queue.

---

# 27. Dashboard

Главный экран может выглядеть примерно так:

```text
Good evening

Today's review
────────────────

23 grammar points due

[ Start Review ]

────────────────

N3 Progress

████████░░ 78%

Grammar mastered
143 / 184

────────────────

Weak areas

わけではない
とは限らない
〜ものの
〜にもかかわらず

────────────────

Recent performance

Recall       86%
Application  72%
Discrimination 61%
```

---

# 28. Метрики

Не стоит оценивать пользователя только по правильным ответам.

Для каждой grammar point:

```text
Recognition
Recall
Application
Discrimination
```

Например:

```text
〜わけではない

Recognition      94%
Recall           81%
Application      68%
Discrimination   42%
```

Это означает:

> Пользователь знает конструкцию, но путает её с похожими конструкциями.

Тогда система должна назначить именно contrastive practice.

---

# 29. Error model

Каждая ошибка должна классифицироваться.

Например:

```text
Error:

Selected:
とは限らない

Correct:
わけではない

Error type:
confusion

Confusion pair:
わけではない ↔ とは限らない
```

Другие категории:

```text
forgot_meaning
forgot_form
wrong_context
similar_grammar_confusion
reading_problem
vocabulary_problem
```

Это позволит сделать действительно adaptive review.

---

# 30. Vocabulary vs Grammar

Важно не обвинять grammar, если пользователь просто не знает слово.

Например вопрос:

> 会社の方針について...

Пользователь не знает:

> 方針（ほうしん）

и из-за этого не понимает предложение.

Это не обязательно grammar error.

Система должна отличать:

```text
Grammar failure
vs
Vocabulary failure
```

При наличии furigana часть таких проблем автоматически исчезает.

---

# 31. AI generation constraints

Для каждого вопроса LLM получает:

```text
Target grammar
JLPT level
Vocabulary level
Context
Required distinction
Forbidden ambiguity
Known user mistakes
Previously used examples
```

Например:

```text
Target:
〜わけではない

Contrast:
〜とは限らない

Level:
N3

Vocabulary:
N5–N3

Task:
Generate a sentence where both forms initially appear plausible,
but exactly one is correct based on the intended meaning.
```

---

# 32. Validation

LLM-generated content нельзя автоматически публиковать.

Нужен validation layer.

Проверки:

### Grammar

- target grammar actually fits;
- target grammar is necessary;
- sentence is grammatical.

### Ambiguity

- distractor не должен тоже подходить;
- не должно быть двух правильных ответов.

### Level

- vocabulary соответствует выбранному уровню;
- grammar не выходит далеко за пределы уровня без необходимости.

### Duplication

- sentence не использовался ранее;
- context не является почти точной копией.

### Naturalness

- японский должен звучать естественно;
- желательно иметь дополнительный validation model / curated examples для сложных случаев.

---

# 33. Curated + AI hybrid

Не обязательно генерировать всё AI.

Можно использовать:

```text
Curated examples
+
Templates
+
AI-generated examples
```

Например для очень важной grammar:

```text
20 verified base examples
+
AI generates 100 variations
```

Это снижает вероятность плохих вопросов.

---

# 34. Templates

Для некоторых конструкций можно создать шаблоны.

Например:

```text
[Assumption] からといって、
[generalization] わけではない。
```

AI заполняет:

```text
有名な大学を卒業したからといって、
仕事ができるわけではない。
```

Это позволяет контролировать grammar logic.

---

# 35. Grammar explanation database

У каждой конструкции должна быть не только definition, но и structured explanation.

```text
Meaning
Formation
Usage
Nuance
Register
Similar grammar
Difference
Common mistakes
Examples
```

Особенно важен блок:

> Compare with...

Например:

```text
わけではない vs とは限らない

わけではない:
частичное отрицание конкретного утверждения

とは限らない:
утверждение, что результат не является гарантированным
```

---

# 36. Grammar graph как основа AI

AI должен использовать graph.

Если пользователь ошибается:

```text
わけではない
→ selected とは限らない
```

система понимает:

```text
confusion edge:
わけではない ↔ とは限らない
```

И повышает вероятность таких вопросов.

То есть AI generation становится **персонализированным**, а не random.

---

# 37. Personal grammar profile

Со временем приложение знает:

```text
Strong:
〜に違いない
〜ことになっている
〜おそれがある

Weak:
〜わけではない
〜とは限らない
〜ものの
〜にもかかわらず
```

И review algorithm работает не только по времени, но и по слабым местам.

---

# 38. Mastery

Можно определить mastery threshold.

Например:

```text
Mastered

Recall ≥ 85%
Application ≥ 80%
Discrimination ≥ 80%
Recent error rate < threshold
```

После mastery interval увеличивается.

Но grammar не удаляется.

Она продолжает получать occasional maintenance reviews.

---

# 39. Forgetting curve

Основная модель:

```text
Learn
 ↓
Recall
 ↓
Correct
 ↓
Longer interval
 ↓
Correct
 ↓
Longer interval
```

Если пользователь ошибся:

```text
Error
 ↓
short interval
 ↓
new context
 ↓
contrastive question
```

Особенно если ошибка была именно confusion error.

---

# 40. Active Recall вместо Passive Exposure

Принцип продукта:

```text
Reading:
"Я это знаю"

не равно

Retrieval:
"Я могу выбрать это сейчас"
```

Поэтому приоритет:

```text
Active question
>
Passive reading
```

Reading examples остаются, но как explanation/support, а не основной метод обучения.

---

# 41. UX одного review question

Пример:

```text
N3 Grammar Review

Question 8 / 20

彼は日本に10年住んでいるからといって、
日本の文化をすべて理解している □□□□□。

A. わけではない
B. わけがない
C. とは限らない
D. に違いない
```

Furigana автоматически показывается только там, где нужно.

После ответа:

```text
〜わけではない

「必ずしも〜ではない」
= не обязательно / не то чтобы

Why:
The sentence partially denies the assumption
that living in Japan means knowing all Japanese culture.

Compare:
とは限らない → result is not guaranteed
わけではない → specific assumption is denied
```

---

# 42. Review interaction

Не нужно делать каждое упражнение длинным.

Цикл:

```text
Question
↓
Answer
↓
Immediate feedback
↓
Next
```

Средняя длина session:

```text
5 min
10 min
20 min
```

Пользователь должен иметь возможность открыть приложение, пройти 5–10 вопросов и закрыть его.

---

# 43. Daily goal

Например:

```text
Daily review:
10 questions
```

или:

```text
15 minutes/day
```

Но цель должна быть вторичной.

Основной двигатель — due reviews.

---

# 44. Notification logic

Можно добавить:

> 12 grammar points are due today.

Но notification не должна превращаться в обычную streak-механику.

Главное — поддержание retrieval.

---

# 45. Progress by JLPT

```text
N3

Grammar:
143 / 184

Mastered:
91

Learning:
32

Weak:
20
```

Отдельно:

```text
Shin Kanzen Master N3

Lessons completed:
12 / 20
```

Это позволяет различать:

**учебный прогресс** и **реальное mastery**.

---

# 46. Progress by grammar category

Можно добавить:

```text
Conditionals
Causality
Contrast
Time
Probability
Modality
Restriction
Comparison
Purpose
Passive/Causative
```

Пользователь может видеть:

> Contrast grammar — weak.

Это полезнее, чем просто N3 = 73%.

---

# 47. Search

Пользователь должен иметь поиск:

```text
わけではない
```

И получить:

```text
Meaning
Formation
Examples
Similar grammar
Past mistakes
Review history
```

---

# 48. Manual review

Пользователь может сказать:

> Я хочу повторить эти 8 конструкций.

Выбирает:

```text
☑ わけではない
☑ とは限らない
☑ ものの
...
```

И запускает custom session.

---

# 49. AI prompt mode

Можно сделать:

> Generate practice

Настройки:

```text
Grammar:
selected

Questions:
10

Difficulty:
Easy / Normal / Hard

Vocabulary:
N3

Furigana:
Adaptive

Mode:
Similar grammar
```

AI генерирует session.

---

# 50. Возможность написать свою грамматику

Пользователь может добавить:

```text
Custom grammar

Expression:
〜に越したことはない

Level:
N2

Notes:
...
```

После чего AI генерирует examples и questions.

---

# 51. Импорт

В дальнейшем:

```text
Anki import
CSV
JSON
Custom grammar list
```

Пользователь может импортировать собственную базу.

---

# 52. Возможная архитектура

## Frontend

Вариант:

```text
Next.js
React
TypeScript
```

Mobile:

```text
React Native / Expo
```

или сначала responsive web app / PWA.

---

## Backend

```text
Python
FastAPI
PostgreSQL
```

---

## AI

Поддерживать abstraction layer:

```text
OpenAI
Anthropic
Google
```

Не привязывать приложение к одному provider.

---

## Infrastructure

```text
PostgreSQL
Redis
Object Storage
Background workers
```

Для первого MVP Redis и отдельные workers можно отложить.

---

# 53. Основные database entities

```text
User

Grammar

GrammarRelation

Curriculum

Lesson

UserGrammar

Review

Question

QuestionAttempt

Vocabulary

UserVocabulary

GeneratedExample
```

---

# 54. UserGrammar

Например:

```text
user_id
grammar_id

status
learning
review
mastered

first_seen
last_reviewed
next_review

ease
interval
repetitions

recall_score
application_score
discrimination_score
```

---

# 55. QuestionAttempt

```text
user_id
question_id
selected_answer
correct_answer

is_correct

response_time

error_type

created_at
```

Это позволяет потом анализировать:

- что пользователь путает;
- какие вопросы слишком простые;
- какие grammar pairs вызывают проблемы;
- какие distractors работают плохо.

---

# 56. Question generation database

Каждый generated question должен храниться.

```text
question_id
grammar_id
question_type
difficulty
sentence
options
correct_option

generation_model
generation_prompt_version

validation_status
created_at
```

Таким образом, один и тот же вопрос не будет бесконечно генерироваться заново.

---

# 57. AI cost optimization

Не нужно генерировать вопрос в момент каждого клика.

Можно:

```text
User finishes Lesson
        ↓
Generate 20–50 questions
        ↓
Validate
        ↓
Store
        ↓
Serve later
```

И затем background generation пополняет queue.

Это значительно дешевле и быстрее.

---

# 58. MVP

Я бы не начинал с N5–N1 и сложной AI-системы.

Первый MVP:

```text
N3
Shin Kanzen Master
```

Только:

1. Grammar database.
2. Lessons.
3. 4-choice tests.
4. SRS.
5. New generated examples.
6. Similar grammar distractors.
7. Furigana.
8. Basic statistics.

Этого уже достаточно для проверки продукта.

---

# 59. MVP user flow

```text
Sign up
 ↓
Choose Shin Kanzen N3
 ↓
Select completed lessons
 ↓
Review queue generated
 ↓
Start review
 ↓
4-choice question
 ↓
Answer
 ↓
Explanation
 ↓
SRS schedules next review
 ↓
Dashboard
```

---

# 60. V2

Добавить:

```text
Grammar Graph
Confusion Sets
Adaptive Furigana
Adaptive difficulty
Weak point detection
AI-generated personalized questions
Vocabulary tracking
```

---

# 61. V3

Добавить:

```text
N5–N1
Multiple curricula
Anki import
Custom grammar
Advanced analytics
AI tutor
Writing practice
Production practice
Speaking practice
```

---

# 62. Возможное расширение до production

После grammar retrieval можно добавить:

### Sentence production

Пользователь получает ситуацию:

> Ты хочешь сказать, что высокая цена не означает хорошее качество.

И должен сам написать предложение.

AI оценивает использование grammar.

Это уже следующий уровень после multiple-choice.

Pipeline:

```text
Recognition
↓
Recall
↓
Application
↓
Discrimination
↓
Production
```

---

# 63. Speaking

В дальнейшем:

```text
AI gives situation
↓
User speaks Japanese
↓
Speech-to-text
↓
Grammar analysis
↓
Feedback
```

Например система специально просит использовать:

> 〜わけではない

и проверяет, смог ли пользователь применить конструкцию.

Это уже не обязательно для MVP.

---

# 64. Главный принцип продукта

Продукт должен отвечать на вопрос:

> «Можешь ли ты использовать эту грамматику сейчас, без подсказки?»

а не:

> «Ты когда-нибудь видел эту грамматику?»

---

# 65. Чем продукт отличается от Anki

Anki:

```text
Card
↓
Remember
↓
Again / Hard / Good / Easy
```

Grammar Trainer:

```text
Grammar
↓
Context
↓
4 candidate grammars
↓
Discrimination
↓
Explanation
↓
Error classification
↓
SRS
↓
Adaptive next question
```

Anki хранит карточки.

Этот продукт хранит **knowledge graph + learner model**.

---

# 66. Чем отличается от обычного учебника

Учебник:

```text
New material
↓
Explanation
↓
Practice
↓
Test
```

Приложение:

```text
Previously learned material
↓
Repeated retrieval
↓
New contexts
↓
Contrastive practice
↓
Long-term retention
```

То есть это companion layer, а не replacement.

---

# 67. Основная формула продукта

```text
Structured curriculum
+
Spaced repetition
+
Active retrieval
+
New contexts
+
Contrastive grammar
+
Adaptive furigana
+
AI generation
+
Learner error model
=
Japanese Grammar Retrieval Trainer
```

---

# 68. Ключевые фичи в порядке важности

### Tier 1 — Core

1. Grammar database.
2. 4-choice questions.
3. SRS.
4. Lesson structure.
5. New examples.
6. Furigana.
7. Review dashboard.

### Tier 2 — Differentiation

8. Grammar relationships.
9. Confusion sets.
10. Contrastive questions.
11. Error classification.
12. Adaptive difficulty.
13. Adaptive furigana.

### Tier 3 — AI

14. AI-generated questions.
15. AI explanations.
16. Personalized question generation.
17. AI validation.
18. Custom grammar generation.

### Tier 4 — Advanced

19. Writing production.
20. Speaking.
21. AI tutor.
22. Full JLPT ecosystem.

---

# 69. Главная продуктовая гипотеза

Гипотеза:

> Японские студенты знают значительно больше грамматики пассивно, чем способны самостоятельно применять. Регулярный spaced retrieval в новых контекстах и contrastive questions по похожим конструкциям способны значительно увеличить active recall и discrimination.

MVP должен проверить именно эту гипотезу.

Не нужно сначала строить огромную AI-платформу.

Нужно проверить:

```text
User studies grammar
        ↓
App schedules it
        ↓
User returns days/weeks later
        ↓
User answers new context
        ↓
User distinguishes similar grammar
        ↓
Retention improves
```

Если этот loop работает, вокруг него уже можно строить полноценный продукт.
