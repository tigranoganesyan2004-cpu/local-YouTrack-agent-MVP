from pathlib import Path
import pandas as pd

from src.config import RAW_DIR


def discover_input_files() -> dict:
    """
    Ищет входные файлы в data/raw.
    Сейчас поддерживаем XLSX и CSV.
    Если есть оба формата, потом склеим их в один DataFrame.
    """
    xlsx_files = sorted(RAW_DIR.glob("*.xlsx"))
    csv_files = sorted(RAW_DIR.glob("*.csv"))

    if not xlsx_files and not csv_files:
        raise FileNotFoundError(
            f"В папке {RAW_DIR} нет XLSX/CSV. Положи туда выгрузку YouTrack."
        )

    return {
        "xlsx": xlsx_files[0] if xlsx_files else None,
        "csv": csv_files[0] if csv_files else None,
    }


def load_xlsx(path: Path):
    """
    Читает Excel-выгрузку.
    """
    return pd.read_excel(path)


def load_csv(path: Path):
    """
    Читает CSV-выгрузку.
    sep=None + engine='python' позволяет pandas самому угадать разделитель.
    """
    return pd.read_csv(path, sep=None, engine="python")


def load_source_dataframe():
    """
    Загружает все доступные источники и склеивает их в один DataFrame.

    Зачем это нужно:
    - иногда у нас есть и XLSX, и CSV;
    - не нужно вручную решать, какой файл брать;
    - вся очистка и дедупликация будет уже после объединения.
    """
    files = discover_input_files()
    frames = []

    if files["xlsx"] is not None:
        frames.append(load_xlsx(files["xlsx"]))

    if files["csv"] is not None:
        frames.append(load_csv(files["csv"]))

    if not frames:
        raise FileNotFoundError("Не найдено входных файлов.")

    df = pd.concat(frames, ignore_index=True, sort=False)
    return df, files