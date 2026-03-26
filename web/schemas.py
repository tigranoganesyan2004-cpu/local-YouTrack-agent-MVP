from pydantic import BaseModel
from typing import Any


class QueryRequest(BaseModel):
    query: str
    mode: str = "auto"  # auto | exact | llm


class ActionResponse(BaseModel):
    ok: bool
    message: str
    data: Any | None = None