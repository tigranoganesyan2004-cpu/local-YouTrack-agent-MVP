# local-YouTrack-agent-MVP

Локальный аналитический агент для работы с выгрузкой задач YouTrack (XLSX/CSV).

Проект предназначен для быстрого поиска задач, нахождения похожих кейсов, проверки дедлайнов, фильтрации по полям и получения структурированного ответа по найденному контексту. Агент работает локально, использует Ollama для генерации и embeddings, FAISS для семантического поиска, SQLite для истории и FastAPI для локального web-интерфейса.

---

## Что делает агент

Текущий pipeline Stage 1:

1. Загружает выгрузку из `data/raw/` (`.xlsx` и/или `.csv`)
2. Нормализует данные и сохраняет:
   - `data/processed/tasks.json`
   - `data/processed/dataset_report.json`
3. Строит FAISS-индекс:
   - `data/index/tasks.index`
   - `data/index/tasks_mapping.json`
4. Принимает запрос пользователя
5. Определяет режим запроса
6. Делает retrieval
7. При необходимости вызывает LLM только по найденному контексту
8. Возвращает структурированный ответ
9. Сохраняет историю в SQLite:
   - `data/history/agent_history.db`

---

## Текущая архитектура

### Data layer
- `src/schema.py` — маппинг колонок выгрузки в внутренние поля
- `src/data_loader.py` — загрузка XLSX/CSV
- `src/data_prepare.py` — нормализация, дедупликация, `semantic_text`, `metadata_text`, quality report

### Retrieval layer
- `src/ollama_client.py` — работа с Ollama (`/api/generate`, `/api/embed`)
- `src/vector_store.py` — построение и загрузка FAISS-индекса
- `src/search_engine.py` — exact / lexical / semantic / hybrid search, дедлайны, related tasks

### Agent layer
- `src/query_parser.py` — разбор запроса и определение режима
- `src/prompts.py` — prompt builder для LLM
- `src/response_parser.py` — разбор и валидация JSON-ответа от LLM
- `src/answer_builder.py` — единый формат ответа
- `src/agent.py` — orchestration: parser → retrieval → LLM/fallback → history

### Persistence
- `src/history_store.py` — SQLite-история запросов

### Interfaces
- `main.py` — CLI-меню и чат
- `web/app.py` — FastAPI backend
- `web/templates/index.html` — HTML интерфейс
- `web/static/app.js` — логика web UI
- `web/static/style.css` — стили

---

## Основные функции

### CLI / агент
- Поиск по ID:
  - `ид EAIST_SGL-350`
  - `показать EAIST_SGL-350`

- Детерминированный поиск без LLM:
  - `точно уведомления`
  - `точно согласование`

- Похожие задачи:
  - `похожие уведомления претензионная работа`

- Анализ новой постановки:
  - `анализ Нужно уведомлять пользователей о просрочке`

- Общий запрос через retrieval + LLM:
  - `общий Какие похожие задачи уже были по уведомлениям`

- Фильтры:
  - `список priority=Высокий`
  - `список workflow_group=review`

- Подсчеты:
  - `количество по workflow_group`
  - `количество по status`

- Дедлайны:
  - `сроки days=14`

### Web UI
В web-интерфейсе доступны:
- просмотр статуса системы;
- подготовка данных;
- пересборка индекса;
- отправка запросов;
- просмотр истории;
- выбор режима:
  - Авто
  - Точный
  - Через LLM

---

## Требования

### ОС
- Windows 10/11
- macOS
- Linux

### ПО
- Python 3.11+
- Ollama
- Git

### Python-зависимости
Устанавливаются из `requirements.txt`, включая:
- pandas
- openpyxl
- numpy
- faiss-cpu
- requests
- python-dotenv
- fastapi
- uvicorn
- jinja2
- pydantic

---

## Переменные окружения

Создай `.env` в корне проекта.

Пример:

```env
OLLAMA_HOST=http://127.0.0.1:11434
GEN_MODEL=qwen2.5:3b
EMBED_MODEL=nomic-embed-text

YOUTRACK_BASE_URL=
YOUTRACK_TOKEN=
YOUTRACK_PROJECT=