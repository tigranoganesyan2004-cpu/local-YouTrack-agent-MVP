# CODEX_WORKFLOW_AND_PROMPTS

## Best use of Codex in this project
Use Codex for narrow, backend-heavy, reviewable slices.

Best for:
- dataset lifecycle
- storage changes
- lightweight helper modules
- schema / metadata additions
- chat-to-dataset binding
- docs and test cleanup

Avoid using Codex first for:
- broad UI redesign
- mixed frontend + backend mega-tasks
- “implement all Stage 1” prompts

## Golden rules for Codex
- one slice at a time
- minimal and localized patch
- do not touch unrelated files
- preserve existing behavior outside the target slice
- do not enable heavy features
- summarize what changed and how to verify it

## Recommended order for Codex usage
1. Active dataset lifecycle
2. Chat-to-dataset binding
3. Lightweight chat memory and LLM gating
4. Docs / benchmark / cleanup

## Prompt 1 — active dataset lifecycle
### English
Task: Implement a Stage 1 active dataset lifecycle.

Context:
- Repo goal: local retrieval-first YouTrack AI agent
- Stage: Stage 1 only
- Constraints: lightweight, grounded, chat-first, one active dataset

Instructions:
- Read all relevant files first.
- Keep changes minimal and localized.
- Do not touch unrelated files.
- Preserve existing behavior unless the task explicitly changes it.
- Return a short plan before editing.
- Then implement.
- Then summarize exactly what changed and how to verify it.

Acceptance criteria:
- introduce active_dataset.json metadata support
- support exactly one active dataset at a time
- replacing the dataset clears old raw / processed / index artifacts
- the new dataset can be prepared and indexed cleanly
- no heavy features are enabled
- existing retrieval-first behavior remains intact

### Русский перевод
Задача: Реализовать lifecycle активного датасета для Stage 1.

Контекст:
- Цель репозитория: локальный retrieval-first YouTrack AI агент
- Этап: только Stage 1
- Ограничения: lightweight, grounded, chat-first, один active dataset

Инструкции:
- Сначала прочитай все релевантные файлы.
- Делай изменения минимальными и локальными.
- Не трогай несвязанные файлы.
- Сохраняй текущее поведение, если задача явно не требует иного.
- Сначала верни короткий план.
- Потом реализуй.
- Потом кратко опиши, что именно изменено и как это проверить.

Критерии приемки:
- добавить поддержку metadata через active_dataset.json
- поддерживать ровно один active dataset одновременно
- замена датасета должна очищать старые raw / processed / index артефакты
- новый датасет должен чисто подготавливаться и индексироваться
- тяжелые функции не должны включаться
- retrieval-first поведение должно сохраниться

## Prompt 2 — chat to dataset binding
### English
Task: Bind chats to dataset_id and introduce archive/read-only behavior for stale chats after dataset replacement.

Requirements:
- minimal and localized patch
- do not redesign the UI in this task
- preserve current behavior outside this slice
- clearly describe data model changes
- summarize how to verify archive behavior

Acceptance criteria:
- chats store dataset_id
- stale chats are marked archived when active dataset changes
- old chats are not used as live context for the new dataset
- opening an old chat remains possible in archive/read-only mode

### Русский перевод
Задача: Привязать чаты к dataset_id и ввести archive/read-only поведение для устаревших чатов после смены датасета.

Требования:
- минимальный и локальный патч
- не делать UI-redesign в рамках этой задачи
- сохранить текущее поведение вне этого slice
- ясно описать изменения модели данных
- описать, как проверить archive behavior

Критерии приемки:
- chats хранят dataset_id
- устаревшие чаты помечаются archived при смене active dataset
- старые чаты не используются как live context для нового датасета
- старые чаты можно открыть в режиме archive/read-only

## Prompt 3 — lightweight chat memory and LLM gating
### English
Task: Implement lightweight chat memory for the same chat_id + dataset_id and narrow LLM usage in Stage 1.

Requirements:
- memory must stay lightweight
- do not carry context across dataset changes
- keep deterministic paths exact
- do not enable deep mode, reranker, critic, or streaming

Acceptance criteria:
- only recent messages from the same chat_id and dataset_id are used
- deterministic list/count/stats/deadline flows do not trigger unnecessary LLM use
- AI synthesis remains grounded in retrieved tasks only

### Русский перевод
Задача: Реализовать lightweight chat memory в пределах одного chat_id + dataset_id и сузить использование LLM в Stage 1.

Требования:
- память должна оставаться легкой
- нельзя переносить контекст через смену dataset
- deterministic paths должны оставаться точными
- не включать deep mode, reranker, critic или streaming

Критерии приемки:
- используются только недавние сообщения того же chat_id и dataset_id
- deterministic сценарии list/count/stats/deadline не триггерят лишний LLM
- AI synthesis остается grounded только на найденных задачах
