from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., description="Текст запроса пользователя")
    mode: str = Field(default="ai_answer", description="Public: ai_answer (AI Answer) | precise (Precise Mode). Internal compat: auto | exact | llm")


class ExportRequest(BaseModel):
    query: str = Field(..., description="Текст запроса для экспорта")
    mode: str = Field(default="ai_answer", description="Public: ai_answer (AI Answer) | precise (Precise Mode). Internal compat: auto | exact | llm")


class ActionResponse(BaseModel):
    ok: bool
    message: str
    data: Any | None = None