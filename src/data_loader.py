from pathlib import Path

import pandas as pd

from src.config import RAW_DIR
from src.schema import REQUIRED_SOURCE_COLUMNS
from src.utils import clean_column_name


def discover_input_files() -> dict:
    """
    Ищет все входные файлы в data/raw.

    Мы читаем все XLSX и CSV, а не только первый файл,
    чтобы потом детерминированно объединить и дедуплицировать записи.
    """
    xlsx_files = sorted(RAW_DIR.glob("*.xlsx"))
    csv_files = sorted(RAW_DIR.glob("*.csv"))

    if not xlsx_files and not csv_files:
        raise FileNotFoundError(
            f"В папке {RAW_DIR} нет XLSX/CSV. Положи туда выгрузку YouTrack."
        )

    return {
        "xlsx": xlsx_files,
        "csv": csv_files,
    }


def normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned.columns = [clean_column_name(col) for col in cleaned.columns]
    return cleaned


def validate_required_columns(df: pd.DataFrame, path: Path) -> None:
    missing = [col for col in REQUIRED_SOURCE_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"В файле {path.name} не хватает обязательных колонок: {', '.join(missing)}"
        )


def attach_source_metadata(df: pd.DataFrame, path: Path, source_type: str) -> pd.DataFrame:
    enriched = df.copy()
    enriched["__source_file"] = path.name
    enriched["__source_path"] = str(path)
    enriched["__source_type"] = source_type
    enriched["__source_row"] = range(2, len(enriched) + 2)
    return enriched


def load_xlsx(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path)
    df = normalize_dataframe_columns(df)
    validate_required_columns(df, path)
    return attach_source_metadata(df, path, "xlsx")


def load_csv(path: Path) -> pd.DataFrame:
    """
    encoding='utf-8-sig' убирает BOM.
    После этого дополнительно чистим названия колонок.
    """
    # Stage 1: keep text decoding lightweight and deterministic.
    # We try UTF-8 first (default path), then CP1251 for legacy CSV exports.
    csv_encodings = ("utf-8-sig", "utf-8", "cp1251")
    last_error = None
    df = None

    for encoding in csv_encodings:
        try:
            df = pd.read_csv(path, sep=None, engine="python", encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc

    if df is None:
        raise ValueError(
            f"Не удалось прочитать CSV {path.name} в кодировках {csv_encodings}. "
            f"Последняя ошибка: {last_error}"
        )

    df = normalize_dataframe_columns(df)
    validate_required_columns(df, path)
    return attach_source_metadata(df, path, "csv")


def load_source_dataframe():
    """
    Возвращает:
    - объединенный DataFrame
    - metadata по источникам
    """
    files = discover_input_files()
    frames = []

    for path in files["xlsx"]:
        frames.append(load_xlsx(path))

    for path in files["csv"]:
        frames.append(load_csv(path))

    if not frames:
        raise FileNotFoundError("Не найдено входных файлов.")

    df = pd.concat(frames, ignore_index=True, sort=False)

    rows_by_source = {
        "xlsx": 0,
        "csv": 0,
    }

    for frame in frames:
        source_type = frame["__source_type"].iloc[0]
        rows_by_source[source_type] += len(frame)

    meta = {
        "xlsx": files["xlsx"],
        "csv": files["csv"],
        "rows_by_source": rows_by_source,
    }

    return df, meta
