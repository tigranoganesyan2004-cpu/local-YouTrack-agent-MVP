import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import dataset_lifecycle


def _patch_data_paths(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    processed_dir = data_dir / "processed"
    index_dir = data_dir / "index"

    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(dataset_lifecycle, "DATA_DIR", data_dir)
    monkeypatch.setattr(dataset_lifecycle, "RAW_DIR", raw_dir)
    monkeypatch.setattr(dataset_lifecycle, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(dataset_lifecycle, "INDEX_DIR", index_dir)
    monkeypatch.setattr(dataset_lifecycle, "ACTIVE_DATASET_JSON", data_dir / "active_dataset.json")

    return {
        "data_dir": data_dir,
        "raw_dir": raw_dir,
        "processed_dir": processed_dir,
        "index_dir": index_dir,
    }


def test_register_and_mark_indexed(monkeypatch, tmp_path):
    paths = _patch_data_paths(monkeypatch, tmp_path)
    raw_file = paths["raw_dir"] / "dataset_a.csv"
    raw_file.write_text("id,summary\n1,Task A\n", encoding="utf-8")

    metadata = dataset_lifecycle.register_prepared_dataset(rows_raw_total=1, tasks_total=1)

    assert metadata["dataset_id"].startswith("ds_")
    assert metadata["source_files"] == ["raw/dataset_a.csv"]
    assert metadata["rows_raw_total"] == 1
    assert metadata["tasks_total"] == 1
    assert metadata["indexed_at"] == ""

    updated = dataset_lifecycle.mark_active_dataset_indexed(tasks_total=2)
    assert updated["indexed_at"]
    assert updated["tasks_total"] == 2

    loaded = dataset_lifecycle.load_active_dataset_metadata()
    assert loaded["dataset_id"] == metadata["dataset_id"]
    assert loaded["indexed_at"] == updated["indexed_at"]


def test_replacement_clears_old_artifacts(monkeypatch, tmp_path):
    paths = _patch_data_paths(monkeypatch, tmp_path)

    old_raw = paths["raw_dir"] / "old_dataset.csv"
    old_raw.write_text("id,summary\n1,Old Task\n", encoding="utf-8")
    old_meta = dataset_lifecycle.register_prepared_dataset(rows_raw_total=1, tasks_total=1)

    (paths["processed_dir"] / ".gitkeep").write_text("", encoding="utf-8")
    (paths["index_dir"] / ".gitkeep").write_text("", encoding="utf-8")
    (paths["processed_dir"] / "tasks.json").write_text("[]", encoding="utf-8")
    (paths["processed_dir"] / "dataset_report.json").write_text("{}", encoding="utf-8")
    (paths["index_dir"] / "tasks.index").write_text("fake", encoding="utf-8")
    (paths["index_dir"] / "tasks_mapping.json").write_text("[]", encoding="utf-8")

    new_raw = paths["raw_dir"] / "new_dataset.csv"
    new_raw.write_text("id,summary\n2,New Task\n", encoding="utf-8")

    info = dataset_lifecycle.prepare_dataset_replacement_if_needed()

    assert info["dataset_replaced"] is True
    assert "raw/old_dataset.csv" in info["raw_removed"]
    assert not old_raw.exists()
    assert new_raw.exists()

    assert not (paths["processed_dir"] / "tasks.json").exists()
    assert not (paths["processed_dir"] / "dataset_report.json").exists()
    assert not (paths["index_dir"] / "tasks.index").exists()
    assert not (paths["index_dir"] / "tasks_mapping.json").exists()
    assert (paths["processed_dir"] / ".gitkeep").exists()
    assert (paths["index_dir"] / ".gitkeep").exists()

    new_meta = dataset_lifecycle.register_prepared_dataset(rows_raw_total=1, tasks_total=1)
    assert new_meta["dataset_id"] != old_meta["dataset_id"]
    assert new_meta["source_files"] == ["raw/new_dataset.csv"]
