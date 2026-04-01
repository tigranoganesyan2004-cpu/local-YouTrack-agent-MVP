# CURSOR_WORKFLOW_AND_PROMPTS

## Best use of Cursor in this project
Use Cursor first for:
- repository reading
- flow discovery
- exact file mapping
- UI slices
- integration slices touching multiple project files

Use two modes:
- Ask mode first
- Agent mode second

Do not start with Agent mode immediately.

## Golden rules for Cursor
- ask first, edit second
- one slice only
- no broad refactor
- no “implement all Stage 1”
- keep changes reviewable
- do not enable deep/streaming/reranker/critic

## Recommended order for Cursor usage
1. UI simplification to two modes
2. sidebar and chat UX
3. Precise Mode quick actions
4. answer cards polish
5. docs / cleanup

## Prompt 1 — Ask mode for Slice 1
### English
Read this repository and prepare a minimal implementation plan for exactly one Stage 1 slice.
Do not edit files yet.

Slice:
Replace the current public exact/auto/llm/deep mode surface with a simple two-mode user-facing contract:
1) AI Answer
2) Precise Mode

Requirements:
- inspect the current web flow and identify where the public mode selector exists
- inspect whether prefix-based mode routing exists in the web path
- identify the exact files that must change
- explain the smallest safe implementation plan
- keep the architecture lightweight
- do not propose unrelated refactors
- list acceptance checks

Return:
1. current flow
2. files to change
3. risks
4. minimal plan
5. verification steps

### Русский перевод
Изучи этот репозиторий и подготовь минимальный план реализации ровно одного slice для Stage 1.
Файлы пока не редактируй.

Slice:
Замени текущую публичную поверхность exact/auto/llm/deep на два простых пользовательских режима:
1) AI Answer
2) Precise Mode

Требования:
- проверь текущий web flow и найди, где находится публичный mode selector
- проверь, есть ли prefix-based mode routing в web path
- укажи точные файлы, которые надо менять
- объясни минимальный безопасный план реализации
- сохрани архитектуру легкой
- не предлагай посторонние рефакторинги
- дай критерии приемки

Верни:
1. текущий flow
2. файлы для изменения
3. риски
4. минимальный план
5. шаги проверки

## Prompt 2 — Agent mode for Slice 1
### English
Implement exactly this Stage 1 slice and keep the patch minimal.

Task:
Replace the current public exact/auto/llm/deep mode surface with a simple two-mode user-facing contract:
- AI Answer
- Precise Mode

Requirements:
- remove the public multi-mode selector from the UI
- remove or stop using prefix-based mode routing from the web UI path, if present
- keep the implementation lightweight
- do not enable streaming, deep mode, reranker, or critic
- do not touch unrelated files
- preserve current behavior outside this slice
- keep the patch reviewable

Expected output:
1. files changed
2. what changed
3. how to run
4. how to verify

### Русский перевод
Реализуй ровно этот Stage 1 slice и сделай патч минимальным.

Задача:
Замени текущую публичную поверхность exact/auto/llm/deep на два простых пользовательских режима:
- AI Answer
- Precise Mode

Требования:
- убери публичный multi-mode selector из UI
- удали или перестань использовать prefix-based mode routing из web UI path, если он есть
- сохрани реализацию легкой
- не включай streaming, deep mode, reranker или critic
- не трогай несвязанные файлы
- сохрани текущее поведение вне рамок этого slice
- патч должен быть удобен для ревью

Ожидаемый вывод:
1. какие файлы изменены
2. что изменено
3. как запускать
4. как проверять

## Prompt 3 — Ask mode for sidebar/chat slice
### English
Read the repository and prepare a minimal implementation plan for the next Stage 1 slice:
introduce chat sessions and a left sidebar with chat history, without yet implementing dataset replacement.

List:
- files to inspect
- current history flow
- minimal storage changes
- minimal UI changes
- risks
- acceptance checks

### Русский перевод
Изучи репозиторий и подготовь минимальный план реализации следующего slice для Stage 1:
ввести chat sessions и левую панель с историей чатов, пока без реализации dataset replacement.

Укажи:
- какие файлы смотреть
- как сейчас устроена история
- какие минимальные изменения хранения нужны
- какие минимальные UI изменения нужны
- риски
- критерии приемки

## Prompt 4 — Agent mode for sidebar/chat slice
### English
Implement the Stage 1 chat sidebar slice with minimal, reviewable changes.

Requirements:
- add chat sessions
- add a left sidebar
- support new/open/delete chat
- keep the UI lightweight
- do not redesign unrelated areas
- do not mix this task with dataset lifecycle
- summarize how to verify behavior

### Русский перевод
Реализуй slice для Stage 1 с chat sidebar минимальными и удобными для ревью изменениями.

Требования:
- добавить chat sessions
- добавить левую панель
- поддержать новый чат / открытие / удаление
- сохранить UI легким
- не переделывать несвязанные зоны
- не смешивать эту задачу с dataset lifecycle
- опиши, как проверить поведение
