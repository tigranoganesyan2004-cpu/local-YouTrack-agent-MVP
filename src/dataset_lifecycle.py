import hashlib
import json
import shutil
from pathlib import Path

from src.config import ACTIVE_DATASET_JSON, DATA_DIR, INDEX_DIR, PROCESSED_DIR, RAW_DIR
from src.utils import ensure_dir, load_json, now_iso, safe_str, save_json


_RAW_EXTENSIONS = {".xlsx", ".csv"}


def _resolve_path(path: Path) -> Path:
    return path.resolve(strict=False)


def _is_within(path: Path, root: Path) -> bool:
    resolved_path = _resolve_path(path)
    resolved_root = _resolve_path(root)
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_raw_files(raw_dir: Path | None = None) -> list[Path]:
    raw_dir = raw_dir or RAW_DIR
    files = []
    for pattern in ("*.xlsx", "*.csv"):
        files.extend(raw_dir.glob(pattern))
    return sorted(
        [path for path in files if path.is_file()],
        key=lambda p: p.name.lower(),
    )


def _build_source_snapshot(raw_dir: Path | None = None) -> list[dict]:
    raw_dir = raw_dir or RAW_DIR
    files = _iter_raw_files(raw_dir=raw_dir)
    snapshot = []

    for path in files:
        rel_path = path.relative_to(DATA_DIR).as_posix() if _is_within(path, DATA_DIR) else path.name
        snapshot.append(
            {
                "path": rel_path,
                "name": path.name,
                "sha256": _hash_file(path),
                "size_bytes": int(path.stat().st_size),
            }
        )

    return snapshot


def _dataset_id_from_snapshot(snapshot: list[dict]) -> str:
    canonical = [
        {"path": safe_str(item.get("path")), "sha256": safe_str(item.get("sha256"))}
        for item in snapshot
    ]
    canonical.sort(key=lambda item: item["path"])
    payload = json.dumps(canonical, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"ds_{digest[:16]}"


def load_active_dataset_metadata() -> dict:
    if not ACTIVE_DATASET_JSON.exists():
        return {}

    try:
        data = load_json(ACTIVE_DATASET_JSON)
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


def save_active_dataset_metadata(metadata: dict) -> None:
    save_json(metadata, ACTIVE_DATASET_JSON)


def _resolve_old_raw_path(path_text: str) -> Path | None:
    text = safe_str(path_text)
    if not text:
        return None

    rel = Path(text)
    if rel.is_absolute():
        candidate = rel
    else:
        parts = list(rel.parts)
        if parts and parts[0].lower() == "data":
            rel = Path(*parts[1:])
        candidate = DATA_DIR / rel

    if not _is_within(candidate, RAW_DIR):
        return None

    return candidate


def _clear_dir_artifacts(directory: Path, suffixes: set[str] | None = None) -> list[str]:
    removed = []
    if not directory.exists():
        return removed

    for path in directory.iterdir():
        if path.name == ".gitkeep":
            continue

        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path.name)
            continue

        if suffixes and path.suffix.lower() not in suffixes:
            continue

        path.unlink(missing_ok=True)
        removed.append(path.name)

    return removed


def clear_processed_and_index_artifacts() -> dict:
    ensure_dir(PROCESSED_DIR)
    ensure_dir(INDEX_DIR)
    return {
        "processed_removed": _clear_dir_artifacts(PROCESSED_DIR),
        "index_removed": _clear_dir_artifacts(INDEX_DIR),
    }


def _clear_stale_raw_files(active_metadata: dict) -> list[str]:
    source_hashes = active_metadata.get("source_hashes", [])
    if not isinstance(source_hashes, list):
        return []

    removed = []
    for item in source_hashes:
        if not isinstance(item, dict):
            continue

        old_hash = safe_str(item.get("sha256"))
        path_text = safe_str(item.get("path"))
        if not old_hash or not path_text:
            continue

        path = _resolve_old_raw_path(path_text)
        if path is None or not path.exists() or path.suffix.lower() not in _RAW_EXTENSIONS:
            continue

        try:
            current_hash = _hash_file(path)
        except Exception:
            continue

        if current_hash != old_hash:
            continue

        path.unlink(missing_ok=True)
        removed.append(path.relative_to(DATA_DIR).as_posix())

    return removed


def prepare_dataset_replacement_if_needed() -> dict:
    active_metadata = load_active_dataset_metadata()
    active_dataset_id = safe_str(active_metadata.get("dataset_id"))
    if not active_dataset_id:
        return {
            "dataset_replaced": False,
            "raw_removed": [],
            "processed_removed": [],
            "index_removed": [],
        }

    snapshot_before = _build_source_snapshot()
    if not snapshot_before:
        return {
            "dataset_replaced": False,
            "raw_removed": [],
            "processed_removed": [],
            "index_removed": [],
        }

    before_id = _dataset_id_from_snapshot(snapshot_before)
    if before_id == active_dataset_id:
        return {
            "dataset_replaced": False,
            "raw_removed": [],
            "processed_removed": [],
            "index_removed": [],
        }

    raw_removed = _clear_stale_raw_files(active_metadata)
    snapshot_after = _build_source_snapshot()
    if not snapshot_after:
        raise FileNotFoundError(
            f"В папке {RAW_DIR} не осталось XLSX/CSV после очистки старого active dataset."
        )

    after_id = _dataset_id_from_snapshot(snapshot_after)
    if after_id == active_dataset_id:
        return {
            "dataset_replaced": False,
            "raw_removed": raw_removed,
            "processed_removed": [],
            "index_removed": [],
        }

    removed = clear_processed_and_index_artifacts()
    return {
        "dataset_replaced": True,
        "raw_removed": raw_removed,
        "processed_removed": removed["processed_removed"],
        "index_removed": removed["index_removed"],
    }


def register_prepared_dataset(rows_raw_total: int, tasks_total: int) -> dict:
    snapshot = _build_source_snapshot()
    if not snapshot:
        raise FileNotFoundError(f"В папке {RAW_DIR} нет XLSX/CSV для active dataset metadata.")

    dataset_id = _dataset_id_from_snapshot(snapshot)
    previous = load_active_dataset_metadata()
    previous_id = safe_str(previous.get("dataset_id"))

    created_at = safe_str(previous.get("created_at"))
    if previous_id != dataset_id or not created_at:
        created_at = now_iso()

    indexed_at = safe_str(previous.get("indexed_at")) if previous_id == dataset_id else ""

    metadata = {
        "dataset_id": dataset_id,
        "source_files": [item["path"] for item in snapshot],
        "source_hashes": [{"path": item["path"], "sha256": item["sha256"]} for item in snapshot],
        "created_at": created_at,
        "prepared_at": now_iso(),
        "indexed_at": indexed_at,
        "rows_raw_total": int(rows_raw_total),
        "tasks_total": int(tasks_total),
    }
    save_active_dataset_metadata(metadata)
    return metadata


def mark_active_dataset_indexed(tasks_total: int | None = None) -> dict:
    metadata = load_active_dataset_metadata()
    if not metadata:
        return {}

    metadata["indexed_at"] = now_iso()
    if tasks_total is not None:
        metadata["tasks_total"] = int(tasks_total)

    save_active_dataset_metadata(metadata)
    return metadata
