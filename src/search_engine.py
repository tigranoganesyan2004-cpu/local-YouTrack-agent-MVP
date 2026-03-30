from __future__ import annotations
 
import math
from datetime import datetime, timedelta
import numpy as np
 
from src.config import TASKS_JSON, USE_RERANKER
from src.utils import load_json, tokenize
from src.vector_store import load_index
from src.ollama_client import ollama_client
from src.reranker import rerank
 
 
def load_tasks() -> list[dict]:
    return load_json(TASKS_JSON)
 
 
def find_task_by_id(issue_id: str) -> dict | None:
    """
    Ищет задачу по ID без учета регистра.
    """
    issue_id = issue_id.strip().upper()
 
    for task in load_tasks():
        task_issue_id = str(task.get("issue_id", "")).upper()
        if task_issue_id == issue_id:
            return task
 
    return None
 
def filter_tasks(
    status: str | None = None,
    status_group: str | None = None,
    workflow_group: str | None = None,
    priority: str | None = None,
    doc_type: str | None = None,
    functional_customer: str | None = None,
    responsible_dit: str | None = None,
) -> list[dict]:
    """
    Фильтрация задач по основным полям.
 
    status_group оставляем для обратной совместимости.
    workflow_group — новое логическое поле, которое станет основным дальше.
    """
    results = []
    for task in load_tasks():
        if status and task["status"].lower() != status.lower():
            continue
 
        if status_group and task.get("status_group", "").lower() != status_group.lower():
            continue
 
        if workflow_group and task.get("workflow_group", "").lower() != workflow_group.lower():
            continue
 
        if priority and task["priority"].lower() != priority.lower():
            continue
 
        if doc_type and task["doc_type"].lower() != doc_type.lower():
            continue
 
        if functional_customer and task["functional_customer"].lower() != functional_customer.lower():
            continue
 
        if responsible_dit and task["responsible_dit"].lower() != responsible_dit.lower():
            continue
 
        results.append(task)
    return results
 
 
def lexical_score(query_tokens: list[str], task: dict) -> float:
    """
    lexical_score теперь считается не по россыпи полей,
    а по трем логическим слоям:
    - issue_id       : очень сильный сигнал
    - semantic_text  : основной смысл
    - metadata_text  : служебные поля, но с меньшим весом
    """
    if not query_tokens:
        return 0.0
 
    fields = [
        ("issue_id", 5.0),
        ("semantic_text", 4.0),
        ("metadata_text", 1.5),
    ]
 
    score = 0.0
    query_set = set(query_tokens)
 
    for field, weight in fields:
        tokens = set(tokenize(task.get(field, "")))
        if not tokens:
            continue
 
        overlap = len(query_set & tokens)
        if overlap:
            score += weight * (overlap / max(len(query_set), 1))
 
    return score
 
def lexical_search(query: str, top_k: int = 5, status_group: str | None = None) -> list[dict]:
    query_tokens = tokenize(query)
    scored = []
    for task in load_tasks():
        if status_group and task["status_group"].lower() != status_group.lower():
            continue
        score = lexical_score(query_tokens, task)
        if score > 0:
            scored.append((score, task))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [task for _, task in scored[:top_k]]
 
def exact_search(query: str, top_k: int = 10) -> list[dict]:
    """
    exact_search — детерминированный поиск без LLM.
 
    Пока для Stage 1 он строится поверх lexical_search.
    Это нужно, чтобы отдельно тестировать retrieval:
    - без генерации,
    - без prompt'ов,
    - без влияния LLM.
    """
    return lexical_search(query, top_k=top_k)
 
def semantic_search(query: str, top_k: int = 5, status_group: str | None = None) -> list[dict]:
    """
    Выполняет векторный поиск по FAISS-индексу.
    Если индекс недоступен или поврежден, возвращает [].
    """
    index, mapping = load_index()
    if index is None:
        return []
 
    tasks = load_tasks()
    tasks_by_id = {t["issue_id"]: t for t in tasks if t.get("issue_id")}
 
    try:
        query_vector = np.array([ollama_client.embed(query)], dtype="float32")
        distances, indices = index.search(query_vector, top_k * 4)
    except Exception:
        return []
 
    issue_ids = []
    seen = set()
 
    for idx in indices[0]:
        if idx == -1:
            continue
 
        if idx >= len(mapping):
            continue
 
        issue_id = mapping[idx].get("issue_id", "")
        if not issue_id or issue_id in seen:
            continue
 
        task = tasks_by_id.get(issue_id)
        if task is None:
            continue
 
        if status_group and task.get("status_group", "").lower() != status_group.lower():
            continue
 
        seen.add(issue_id)
        issue_ids.append(issue_id)
 
        if len(issue_ids) >= top_k:
            break
 
    return [tasks_by_id[iid] for iid in issue_ids if iid in tasks_by_id]
 
def rrf_fuse(rankings: list[list[str]], k: int = 60) -> list[str]:
    scores = {}
    for ranking in rankings:
        for rank, issue_id in enumerate(ranking, start=1):
            scores[issue_id] = scores.get(issue_id, 0.0) + 1.0 / (k + rank)
    return [issue_id for issue_id, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]
 
def hybrid_search(query: str, top_k: int = 5, status_group: str | None = None) -> list[dict]:
    """
    Комбинирует lexical и semantic поиск через RRF, затем опционально
    применяет cross-encoder re-ranking для финального ранжирования.
 
    Без re-ranking: возвращает top_k задач по RRF-score.
    С re-ranking (USE_RERANKER=true): собирает больше кандидатов (top_k * 3),
    прогоняет их через CrossEncoder и возвращает top_k лучших.
    Это улучшает качество топ результатов, особенно при коротких запросах,
    где lexical и semantic сигналы расходятся.
    """
    tasks = load_tasks()
    tasks_by_id = {t["issue_id"]: t for t in tasks}
 
    lexical_ids = [
        t["issue_id"]
        for t in lexical_search(query, top_k=top_k * 3, status_group=status_group)
    ]
 
    semantic_ids = [
        t["issue_id"]
        for t in semantic_search(query, top_k=top_k * 3, status_group=status_group)
    ]
 
    fused_ids = rrf_fuse([lexical_ids, semantic_ids])
 
    # Если re-ranking включён — собираем больше кандидатов для второго прохода.
    # CrossEncoder сам выберет top_k из них с лучшим качеством.
    candidate_limit = top_k * 3 if USE_RERANKER else top_k
 
    seen = set()
    candidates = []
 
    for issue_id in fused_ids:
        if issue_id in seen:
            continue
        seen.add(issue_id)
 
        task = tasks_by_id.get(issue_id)
        if task:
            candidates.append(task)
 
        if len(candidates) >= candidate_limit:
            break
 
    # Re-ranking: второй проход через CrossEncoder, если включён и есть смысл.
    if USE_RERANKER and len(candidates) > 1:
        # rerank() сам обрабатывает fallback если модель недоступна.
        candidates = rerank(query, candidates, top_k=top_k)
    else:
        candidates = candidates[:top_k]
 
    return candidates
 
 
def find_related_tasks(base_task: dict, limit: int = 5) -> list[dict]:
    scored = []
    base_tokens = tokenize(base_task.get("summary", "") + " " + base_task.get("description", ""))
    for task in load_tasks():
        if task["issue_id"] == base_task["issue_id"]:
            continue
        score = 0.0
        if task["functional_customer"] and task["functional_customer"] == base_task["functional_customer"]:
            score += 2.0
        if task["doc_type"] and task["doc_type"] == base_task["doc_type"]:
            score += 1.5
        if task["responsible_dit"] and task["responsible_dit"] == base_task["responsible_dit"]:
            score += 1.0
        if task["status_group"] and task["status_group"] == base_task["status_group"]:
            score += 0.8
        score += lexical_score(base_tokens, task)
        if score > 0:
            scored.append((score, task))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [task for _, task in scored[:limit]]
 
 
def aggregate_counts(field: str, tasks: list[dict]) -> list[tuple[str, int]]:
    """
    Считает количество задач по значению указанного поля.
    Если поля нет, значение считается пустым.
    """
    counter = {}
    for task in tasks:
        value = task.get(field, "") or "<пусто>"
        counter[value] = counter.get(value, 0) + 1
 
    return sorted(counter.items(), key=lambda x: x[1], reverse=True)
 
 
def upcoming_deadlines(days: int = 14) -> list[dict]:
    now = datetime.now()
    threshold = now + timedelta(days=days)
    results = []
 
    date_fields = [
        ("deadline_dit", "ДИТ"),
        ("deadline_gku", "ГКУ"),
        ("deadline_dkp", "ДКП"),
        ("deadline_dep", "ДЭПиР"),
        ("deadline_fix_comments", "Устранение замечаний"),
    ]
 
    for task in load_tasks():
        for field, label in date_fields:
            raw = task.get(field, "")
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(raw.replace("T", " "))
            except ValueError:
                continue
            if now <= dt <= threshold:
                results.append({
                    "issue_id": task["issue_id"],
                    "summary": task["summary"],
                    "status": task["status"],
                    "deadline_field": field,
                    "deadline_label": label,
                    "deadline_value": raw,
                    "responsible_dit": task.get("responsible_dit", ""),
                    "functional_customer": task.get("functional_customer", ""),
                })
 
    results.sort(key=lambda x: x["deadline_value"])
    return results