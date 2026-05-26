from __future__ import annotations

from pathlib import Path

import pandas as pd

from utils import missing_required_columns, normalize_columns, normalize_rate


CSV_ENCODINGS = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
PRIVATE_DATA_NAMES = ["liverintheriver", "\ud638\uc218\uc704\ubc14\uc704"]


def read_csv_flex(path_or_file) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in CSV_ENCODINGS:
        try:
            return pd.read_csv(path_or_file, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    return pd.read_csv(path_or_file)


def load_excel(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    frames: list[pd.DataFrame] = []
    xls = pd.ExcelFile(path)
    for sheet in xls.sheet_names:
        raw = pd.read_excel(path, sheet_name=sheet)
        raw = raw.rename(columns=normalize_columns(raw.columns))
        if {"title", "base_price", "expected_to_base_ratio"}.issubset(raw.columns):
            raw = raw.dropna(subset=["title", "base_price", "expected_to_base_ratio"]).copy()
            if raw.empty:
                continue
            generated_ids = pd.Series([f"{path.stem}-{sheet}-{i + 1}" for i in range(len(raw))], index=raw.index)
            if "notice_id" not in raw.columns:
                raw["notice_id"] = generated_ids
            else:
                raw["notice_id"] = raw["notice_id"].replace("", pd.NA).fillna(generated_ids)
            raw["expected_price"] = raw["base_price"] * raw["expected_to_base_ratio"]
            raw["adjustment_rate"] = raw["expected_to_base_ratio"] * 100
            raw["lower_rate"] = raw.get("lower_rate", 87.745)
            raw["source_file"] = path.name
            frames.append(raw)
    if not frames:
        raise ValueError(f"No usable bid rows found in {path.name}.")
    return prepare_data(pd.concat(frames, ignore_index=True))


def find_private_data_files(base_dir: str | Path = ".") -> list[Path]:
    base_dir = Path(base_dir)
    candidates: list[Path] = []
    for data_name in PRIVATE_DATA_NAMES:
        for pattern in [
            f"{data_name}*.xlsx",
            f"{data_name}*.xls",
            f"{data_name}*.csv",
        ]:
            candidates.extend(base_dir.glob(pattern))

        data_dir = base_dir / data_name
        if data_dir.exists():
            for pattern in ["*.xlsx", "*.xls", "*.csv"]:
                candidates.extend(data_dir.glob(pattern))

    return sorted({path for path in candidates if path.is_file()})


def load_local_bid_data(base_dir: str | Path = ".") -> pd.DataFrame:
    candidates = find_private_data_files(base_dir)
    if not candidates:
        raise FileNotFoundError(
            "No private bid data file found. Put liverintheriver.xlsx or liverintheriver.csv in the app folder."
        )

    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    for path in candidates:
        try:
            if path.suffix.lower() in [".xlsx", ".xls"]:
                frames.append(load_excel(path))
            elif path.suffix.lower() == ".csv":
                df = prepare_data(read_csv_flex(path))
                df["source_file"] = path.name
                frames.append(df)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")

    if frames:
        return prepare_data(pd.concat(frames, ignore_index=True))

    raise ValueError("Private bid data files were found but could not be read:\n" + "\n".join(errors))


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.rename(columns=normalize_columns(df.columns))
    if "adjustment_rate" not in df.columns and "expected_to_base_ratio" in df.columns:
        df["adjustment_rate"] = pd.to_numeric(df["expected_to_base_ratio"], errors="coerce") * 100
    if "expected_price" not in df.columns and {"base_price", "adjustment_rate"}.issubset(df.columns):
        df["expected_price"] = (
            pd.to_numeric(df["base_price"], errors="coerce")
            * pd.to_numeric(df["adjustment_rate"], errors="coerce")
            / 100
        )
    if "lower_rate" not in df.columns:
        df["lower_rate"] = 87.745

    missing = missing_required_columns(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    numeric_columns = [
        "base_price",
        "expected_price",
        "lower_rate",
        "minimum_bid_price",
        "winning_price",
        "bid_rate",
        "participant_count",
        "adjustment_rate",
        "household_count",
    ]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["lower_rate"] = df["lower_rate"].map(normalize_rate)
    df["adjustment_rate"] = df["adjustment_rate"].fillna(df["expected_price"] / df["base_price"] * 100)

    if "minimum_bid_price" not in df.columns:
        df["minimum_bid_price"] = df["expected_price"] * df["lower_rate"] / 100
    if "opening_date" in df.columns:
        df["opening_date"] = pd.to_datetime(df["opening_date"], errors="coerce")

    return df.dropna(subset=["base_price", "expected_price", "lower_rate", "adjustment_rate"])
