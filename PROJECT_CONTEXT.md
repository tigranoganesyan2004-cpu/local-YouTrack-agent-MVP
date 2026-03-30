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

### LLM-слой
- prompt builder
- structured JSON output
- parser + normalization
- fallback при кривом ответе модели
- защита `used_issue_ids` от галлюцинаций

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
- `/api/history`

---

## Структура проекта

### Важные файлы
- `main.py` — CLI меню
- `src/data_prepare.py` — подготовка данных
- `src/vector_store.py` — индекс
- `src/search_engine.py` — retrieval
- `src/query_parser.py` — intent parsing
- `src/agent.py` — orchestration
- `src/prompts.py` — prompts
- `src/response_parser.py` — разбор LLM JSON
- `src/answer_builder.py` — итоговый формат ответа
- `src/history_store.py` — SQLite история
- `web/app.py` — FastAPI backend
- `web/service.py` — адаптер для Web UI
- `web/templates/index.html` — шаблон страницы
- `web/static/app.js` — frontend логика
- `web/static/style.css` — стили

---

## Как запускать

### CLI
```bash
python main.py