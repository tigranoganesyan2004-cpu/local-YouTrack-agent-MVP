# PROJECT_CONTEXT.md

## Что это за проект

Это локальный YouTrack AI-agent MVP для анализа задач по выгрузке YouTrack.

Текущий проект — Stage 1:
- источник данных: локальная выгрузка XLSX/CSV в `data/raw/`
- подготовка данных: `tasks.json`, `dataset_report.json`
- индекс: FAISS по embeddings
- агент: retrieval-first
- история: SQLite
- интерфейсы: CLI + локальный FastAPI Web UI

Проект НЕ использует живой YouTrack API в рабочем pipeline на текущем этапе.
`src/youtrack_api.py` есть, но это заготовка под Stage 2.

---

## Главная архитектурная идея

Агент работает по принципу retrieval-first:

1. сначала данные нормализуются;
2. потом строится индекс;
3. потом пользователь задает запрос;
4. агент определяет режим;
5. сначала ищет релевантные задачи;
6. только после retrieval может вызываться LLM;
7. LLM не должна фантазировать вне найденного контекста.

Это не “общий чат-бот”, а локальный аналитический инструмент по задачам.

---

## Что уже реализовано

### Подготовка данных
- чтение XLSX / CSV
- маппинг колонок в внутреннюю схему
- дедупликация по `issue_id`
- `raw_status`, `status_group`, `workflow_group`
- `semantic_text` и `metadata_text`
- сохранение `tasks.json` и `dataset_report.json`

### Поиск
- поиск по ID
- exact / deterministic search
- lexical search
- semantic search
- hybrid search (RRF)
- list / count / deadlines
- cross-encoder reranking через `src/reranker.py` (опционально)

### LLM-слой
- prompt builder
- structured JSON output
- parser + normalization
- fallback при кривом ответе модели
- защита `used_issue_ids` от галлюцинаций
- LLM intent classification в `src/query_parser.py` для сложных свободных запросов

### История
SQLite история сохраняет:
- `created_at`
- `query_text`
- `query_mode`
- `answer_text`
- `found_issue_ids`
- `retrieved_candidates`
- `duration_ms`
- `llm_used`
- `error_text`

### Web UI
FastAPI + HTML/CSS/JS:
- `/api/status`
- `/api/prepare`
- `/api/rebuild-index`
- `/api/query`
- `/api/query-stream`
- `/api/history`

Поддерживается streaming ответа для LLM-режимов через SSE.

---

## Структура проекта

### Важные файлы
- `main.py` — CLI меню
- `src/data_prepare.py` — подготовка данных
- `src/vector_store.py` — индекс
- `src/search_engine.py` — retrieval
- `src/query_parser.py` — intent parsing
- `src/reranker.py` — cross-encoder reranking
- `src/agent.py` — orchestration
- `src/prompts.py` — prompts
- `src/response_parser.py` — разбор LLM JSON
- `src/answer_builder.py` — итоговый формат ответа
- `src/history_store.py` — SQLite история
- `src/ollama_client.py` — генерация / embeddings / streaming
- `web/app.py` — FastAPI backend
- `web/service.py` — адаптер для Web UI
- `web/templates/index.html` — шаблон страницы
- `web/static/app.js` — frontend логика
- `web/static/style.css` — стили
- `tests/test_query_parser.py` — тесты intent parsing

---

## Какие режимы есть у агента

Поддерживаемые mode:
- `task_by_id`
- `exact_search`
- `similar`
- `analyze_new_task`
- `general_search`
- `list`
- `count`
- `deadlines`
- `help`

Пользовательские команды в основном русские:
- `ид ...`
- `показать ...`
- `точно ...`
- `похожие ...`
- `анализ ...`
- `общий ...`
- `список ...`
- `количество по ...`
- `сроки ...`

---

## Что важно не выдумывать

Если анализирует новый помощник / новый чат / Cursor:

1. Нельзя говорить, что YouTrack API уже подключен в рабочий pipeline.
   Это не так.

2. Нельзя говорить, что есть production-ready server-side cancellation long-running запроса.
   На текущем этапе нет полноценной серверной остановки как job manager.

3. Нельзя говорить, что проект production-ready.
   Это сильный Stage 1 MVP, но не production.

4. Нельзя говорить, что есть CI / Docker / полный test coverage,
   если это отдельно не добавили.

5. Нельзя приписывать агенту дообучение модели.
   Сейчас это retrieval + local LLM + reranking.

---

## Текущие главные ограничения

- пока нет живого sync с YouTrack API в рабочем pipeline;
- нет CI;
- нет Docker;
- нет полного набора автотестов;
- stop в web — пока UX-уровень, а не полноценный backend job cancellation;
- качество ответов сильно зависит от качества `semantic_text` и retrieval.

---

## Ближайшие приоритеты

### High impact / low effort
- поддерживать консистентность CLI и SQLite history
- удерживать единые дефолты `.env.example` и `src/config.py`
- честный health-check Ollama через `/api/tags`
- `duration_ms` во всех ответах
- улучшение устойчивости импортов и UI

### High impact / medium effort
- полноценный stop/cancel через jobs + polling
- улучшение фильтров с кавычками и более умным parsing
- better structured web output
- observability по retrieval/LLM pipeline

### Strategic
- тесты на search_engine / web layer
- CI
- Stage 2: YouTrack sync
- attachments / links / chunk-based retrieval

---

## Как запускать

### CLI
```bash
python main.py