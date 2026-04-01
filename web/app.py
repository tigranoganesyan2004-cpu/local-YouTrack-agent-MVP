from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.history_store import init_history_db
from web.schemas import CreateChatRequest, ExportRequest, QueryRequest
from web.service import (
    create_chat_action,
    delete_chat_action,
    export_results_action,
    get_chat_messages_action,
    get_history_action,
    get_system_status,
    get_ui_bootstrap_action,
    list_chats_action,
    prepare_data_action,
    rebuild_index_action,
    run_agent_web,
    search_suggestions_action,
    stream_agent_service,
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="YouTrack Agent Web UI")


@app.on_event("startup")
def on_startup():
    init_history_db()

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.get("/api/status")
def api_status():
    """
    Backward-compatible endpoint.

    Старый фронт продолжит работать, но теперь в data приедут и KPI/dashboard.
    """
    return {
        "ok": True,
        "message": "Статус системы получен",
        "data": get_system_status(),
    }


@app.get("/api/ui-bootstrap")
def api_ui_bootstrap():
    """
    Новый endpoint для будущего UI.

    Возвращает:
    - status
    - dashboard
    - examples
    - lookups
    """
    try:
        data = get_ui_bootstrap_action()
        return {
            "ok": True,
            "message": "UI bootstrap получен",
            "data": data,
        }
    except Exception as e:
        return {
            "ok": False,
            "message": f"Ошибка получения UI bootstrap: {e}",
            "data": None,
        }


@app.get("/api/suggestions")
def api_suggestions(
    q: str = Query(default="", description="Текст для подсказок"),
    limit: int = Query(default=10, ge=1, le=50),
):
    """
    Подсказки для автодополнения.
    """
    try:
        data = search_suggestions_action(q, limit=limit)
        return {
            "ok": True,
            "message": "Подсказки получены",
            "data": data,
        }
    except Exception as e:
        return {
            "ok": False,
            "message": f"Ошибка получения подсказок: {e}",
            "data": None,
        }


@app.post("/api/prepare")
def api_prepare():
    try:
        data = prepare_data_action()
        return {
            "ok": True,
            "message": "Подготовка данных завершена",
            "data": data,
        }
    except Exception as e:
        return {
            "ok": False,
            "message": f"Ошибка подготовки данных: {e}",
            "data": None,
        }


@app.post("/api/rebuild-index")
def api_rebuild_index():
    try:
        data = rebuild_index_action()
        return {
            "ok": True,
            "message": "Индекс пересобран",
            "data": data,
        }
    except Exception as e:
        return {
            "ok": False,
            "message": f"Ошибка пересборки индекса: {e}",
            "data": None,
        }


@app.post("/api/query")
def api_query(payload: QueryRequest):
    """
    Нестріминговый endpoint.
    Подходит и для текущего фронта, и для будущих сценариев.
    """
    try:
        result = run_agent_web(payload.query, payload.mode)
        return {
            "ok": True,
            "message": "Ответ получен",
            "data": result,
        }
    except Exception as e:
        return {
            "ok": False,
            "message": f"Ошибка обработки запроса: {e}",
            "data": None,
        }


@app.post("/api/query-stream")
def api_query_stream(payload: QueryRequest):
    """
    Стриминговый endpoint (SSE).

    Для LLM-режимов шлёт токены по мере генерации,
    затем финальный структурированный result.
    Для остальных режимов — сразу отдаёт готовый result.
    """
    def event_generator():
        yield from stream_agent_service(payload.query, payload.mode, chat_id=payload.chat_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/export-results")
def api_export_results(payload: ExportRequest):
    """
    Экспортирует результат запроса в CSV.

    На этом этапе сервер уже умеет экспортировать:
    - tasks
    - items (overdue/deadlines)
    - count/stats
    """
    try:
        content, filename = export_results_action(payload.query, payload.mode)

        return StreamingResponse(
            BytesIO(content),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )
    except Exception as e:
        return {
            "ok": False,
            "message": f"Ошибка экспорта результатов: {e}",
            "data": None,
        }


@app.get("/api/history")
def api_history(limit: int = 20):
    try:
        rows = get_history_action(limit=limit)
        return {
            "ok": True,
            "message": "История получена",
            "data": rows,
        }
    except Exception as e:
        return {
            "ok": False,
            "message": f"Ошибка чтения истории: {e}",
            "data": None,
        }


# ── Chat session endpoints ───────────────────────────────────────

@app.post("/api/chats")
def api_create_chat(payload: CreateChatRequest):
    try:
        data = create_chat_action(title=payload.title)
        return {"ok": True, "message": "Чат создан", "data": data}
    except Exception as e:
        return {"ok": False, "message": f"Ошибка создания чата: {e}", "data": None}


@app.get("/api/chats")
def api_list_chats(limit: int = Query(default=50, ge=1, le=200)):
    try:
        data = list_chats_action(limit=limit)
        return {"ok": True, "message": "Список чатов", "data": data}
    except Exception as e:
        return {"ok": False, "message": f"Ошибка получения чатов: {e}", "data": None}


@app.get("/api/chats/{chat_id}/messages")
def api_chat_messages(chat_id: str):
    try:
        data = get_chat_messages_action(chat_id)
        return {"ok": True, "message": "Сообщения чата", "data": data}
    except Exception as e:
        return {"ok": False, "message": f"Ошибка получения сообщений: {e}", "data": None}


@app.delete("/api/chats/{chat_id}")
def api_delete_chat(chat_id: str):
    try:
        deleted = delete_chat_action(chat_id)
        if not deleted:
            return {"ok": False, "message": "Чат не найден", "data": None}
        return {"ok": True, "message": "Чат удалён", "data": {"id": chat_id}}
    except Exception as e:
        return {"ok": False, "message": f"Ошибка удаления чата: {e}", "data": None}