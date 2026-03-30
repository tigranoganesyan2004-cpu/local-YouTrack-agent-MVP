"""
reranker.py — второй проход после hybrid_search.
 
Использует CrossEncoder (cross-encoder/ms-marco-MiniLM-L-6-v2) для
переранжирования кандидатов, уже отобранных через RRF.
 
Модель загружается лениво — при первом вызове rerank().
Это значит:
  - старт приложения не замедляется;
  - если sentence-transformers не установлен — fallback без ошибок;
  - повторные вызовы используют уже загруженную модель (синглтон).
 
Отключить через .env: USE_RERANKER=false
"""
 
from __future__ import annotations
 
# Синглтон модели. None = не загружена или недоступна.
_cross_encoder = None
# Флаг: была ли попытка загрузки (чтобы не повторять её при каждом вызове).
_load_attempted = False
 
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
 
 
def _get_encoder():
    """
    Возвращает инстанс CrossEncoder, загружая его при первом вызове.
    При любой ошибке (нет библиотеки, нет интернета, нет модели в кэше)
    возвращает None — вызывающий код получит безопасный fallback.
    """
    global _cross_encoder, _load_attempted
 
    if _load_attempted:
        return _cross_encoder
 
    _load_attempted = True
 
    try:
        from sentence_transformers import CrossEncoder  # noqa: PLC0415
        _cross_encoder = CrossEncoder(RERANKER_MODEL)
    except Exception:
        # sentence-transformers не установлен, модель недоступна,
        # нет подключения — любой из этих случаев обрабатываем молча.
        _cross_encoder = None
 
    return _cross_encoder
 
 
def rerank(query: str, tasks: list[dict], top_k: int = 5) -> list[dict]:
    """
    Переранжирует список задач по релевантности запросу через CrossEncoder.
 
    Принимает:
        query  — текст пользовательского запроса
        tasks  — кандидаты после hybrid_search (уже без дублей)
        top_k  — сколько задач вернуть
 
    Возвращает:
        Список задач, отсортированных по убыванию score CrossEncoder,
        усечённый до top_k.
 
    Fallback:
        Если модель недоступна или произошла любая ошибка —
        возвращает tasks[:top_k] без изменения порядка.
    """
    if len(tasks) <= 1:
        return tasks[:top_k]
 
    encoder = _get_encoder()
    if encoder is None:
        return tasks[:top_k]
 
    try:
        # Формируем пары (запрос, текст задачи) для CrossEncoder.
        # semantic_text — основное смысловое поле, самое подходящее для этого.
        pairs = [
            (query, task.get("semantic_text", "") or "")
            for task in tasks
        ]
 
        scores = encoder.predict(pairs)
 
        # Сортируем по score по убыванию и берём top_k
        ranked = sorted(
            zip(scores, tasks),
            key=lambda x: float(x[0]),
            reverse=True,
        )
        return [task for _, task in ranked[:top_k]]
 
    except Exception:
        # Если predict упал (неожиданный формат, OOM и т.д.) — fallback.
        return tasks[:top_k]