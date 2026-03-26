import hashlib

try:
    import faiss  # type: ignore
except Exception:
    faiss = None

import numpy as np

from src.config import TASKS_JSON, FAISS_INDEX_FILE, FAISS_MAPPING_FILE
from src.utils import load_json, save_json, ensure_dir
from src.ollama_client import ollama_client


# vector_store.py отвечает за построение, сохранение и загрузку
# векторного индекса задач для семантического поиска.


def make_semantic_hash(text: str) -> str:
    """
    Хэш semantic_text нужен для будущей инкрементальной переиндексации:
    если текст не изменился, embedding можно не пересчитывать.
    """
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def save_index(index, mapping):
    """
    Сохраняет FAISS-индекс и mapping на диск.
    """
    if faiss is None:
        raise RuntimeError("faiss-cpu не установлен. Установи зависимости из requirements.txt.")

    ensure_dir(FAISS_INDEX_FILE.parent)
    ensure_dir(FAISS_MAPPING_FILE.parent)

    faiss.write_index(index, str(FAISS_INDEX_FILE))
    save_json(mapping, FAISS_MAPPING_FILE)


def load_index():
    """
    Загружает индекс и mapping, если оба файла существуют и консистентны.

    Если индекс битый или mapping не совпадает по длине,
    лучше вернуть (None, []) и не ломать поиск.
    """
    if faiss is None:
        return None, []

    if not FAISS_INDEX_FILE.exists() or not FAISS_MAPPING_FILE.exists():
        return None, []

    try:
        index = faiss.read_index(str(FAISS_INDEX_FILE))
        mapping = load_json(FAISS_MAPPING_FILE)
    except Exception:
        return None, []

    if not isinstance(mapping, list):
        return None, []

    # Проверяем базовую консистентность:
    # число записей в mapping должно совпадать с числом векторов в индексе.
    try:
        if index.ntotal != len(mapping):
            return None, []
    except Exception:
        return None, []

    return index, mapping

def has_ready_index() -> bool:
    """
    Проверяет, что индекс реально готов к использованию.

    Условия:
    - индекс существует
    - mapping существует
    - load_index() вернул валидные данные
    - mapping не пустой
    """
    index, mapping = load_index()
    return index is not None and isinstance(mapping, list) and len(mapping) > 0

def rebuild_index():
    """
    Полностью пересобирает индекс:
    - читает tasks.json
    - берет semantic_text
    - получает embeddings
    - собирает FAISS
    - сохраняет индекс и mapping

    Возвращает краткий отчет по индексации.
    """
    if faiss is None:
        raise RuntimeError("faiss-cpu не установлен. Установи зависимости из requirements.txt.")

    tasks = load_json(TASKS_JSON)
    if not isinstance(tasks, list):
        raise ValueError("tasks.json имеет неверный формат: ожидается список задач.")

    vectors = []
    mapping = []

    total_tasks = len(tasks)
    skipped_empty = 0
    skipped_bad_vector = 0
    embedding_errors = 0
    expected_dim = None

    for task in tasks:
        semantic_text = str(task.get("semantic_text", "")).strip()

        # Пустой semantic_text не должен попадать в индекс,
        # иначе retrieval будет засоряться мусором.
        if not semantic_text:
            skipped_empty += 1
            continue

        try:
            vector = ollama_client.embed(semantic_text)
        except Exception as e:
            print(f"❌ Ошибка эмбеддинга для задачи {task.get('issue_id')}: {e}")
            embedding_errors += 1
            continue

        # Проверяем, что embedding вообще получен.
        if not vector or not isinstance(vector, list):
            skipped_bad_vector += 1
            continue

        # Проверяем размерность.
        if expected_dim is None:
            expected_dim = len(vector)

        if len(vector) != expected_dim:
            print(
                f"❌ Некорректная размерность эмбеддинга для задачи {task.get('issue_id')}: "
                f"{len(vector)} вместо {expected_dim}"
            )
            skipped_bad_vector += 1
            continue

        vectors.append(vector)
        mapping.append({
            "issue_id": task.get("issue_id", ""),
            "status_group": task.get("status_group", ""),
            "workflow_group": task.get("workflow_group", ""),
            "semantic_hash": make_semantic_hash(semantic_text),
        })

    if not vectors:
        raise ValueError("Нет задач для индексации: все задачи пустые или embeddings не получены.")

    np_vectors = np.array(vectors, dtype="float32")

    # Для Stage 1 оставляем самый простой и точный индекс без обучения.
    index = faiss.IndexFlatL2(np_vectors.shape[1])
    index.add(np_vectors)

    save_index(index, mapping)

    report = {
        "tasks_total": total_tasks,
        "indexed_total": len(vectors),
        "skipped_empty_semantic_text": skipped_empty,
        "skipped_bad_vector": skipped_bad_vector,
        "embedding_errors": embedding_errors,
        "embedding_dim": int(np_vectors.shape[1]),
    }

    return report