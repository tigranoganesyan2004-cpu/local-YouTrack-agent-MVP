from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.schemas import QueryRequest
from web.service import (
    get_system_status,
    prepare_data_action,
    rebuild_index_action,
    run_agent_web,
    get_history_action,
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="YouTrack Agent Web UI")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


@app.get("/api/status")
def api_status():
    return {
        "ok": True,
        "message": "Статус системы получен",
        "data": get_system_status(),
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