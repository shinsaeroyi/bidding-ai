from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from utils import missing_required_columns, normalize_columns, normalize_rate


def generate_sample_data(n: int = 300, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    lower_rates = np.array([86.745, 87.745, 88.000, 88.745])
    base_prices = rng.lognormal(mean=np.log(350_000_000), sigma=0.75, size=n)
    base_prices = np.clip(base_prices, 50_000_000, 3_000_000_000).round(-3)
    selected_rates = rng.choice(lower_rates, size=n, p=[0.2, 0.55, 0.1, 0.15])
    adjustment_rates = np.clip(rng.normal(100.0, 0.72, size=n), 97.0, 103.0)
    expected_prices = (base_prices * adjustment_rates / 100).round()
    min_bid_prices = (expected_prices * selected_rates / 100).round()
    bid_prices = min_bid_prices + rng.normal(1_200_000, 1_500_000, size=n)
    bid_prices = np.maximum(bid_prices, min_bid_prices - rng.uniform(0, 800_000, size=n)).round()

    df = pd.DataFrame(
        {
            "notice_id": [f"SAMPLE-{i:05d}" for i in range(1, n + 1)],
            "title": [f"Sample construction management bid {i}" for i in range(1, n + 1)],
            "agency": rng.choice(["Seoul", "Gyeonggi", "Busan", "LH", "Korea Expressway"], size=n),
            "region": rng.choice(["Seoul", "Gyeonggi", "Busan", "Chungcheong", "Jeolla", "Gyeongsang"], size=n),
            "service_type": rng.choice(["CM", "Construction-stage CM", "Supervision"], size=n),
            "base_price": base_prices,
            "expected_price": expected_prices,
            "lower_rate": selected_rates,
            "minimum_bid_price": min_bid_prices,
            "winning_price": bid_prices,
            "bid_rate": (bid_prices / expected_prices * 100).round(3),
            "participant_count": rng.integers(12, 180, size=n),
            "opening_date": pd.date_range("2024-01-01", periods=n, freq="4D"),
            "preliminary_range": "+/-3%",
            "is_winner": rng.choice(["Y", "N"], size=n, p=[0.08, 0.92]),
            "is_first_rank": rng.choice(["Y", "N"], size=n, p=[0.1, 0.9]),
        }
    )
    df["adjustment_rate"] = (df["expected_price"] / df["base_price"] * 100).round(5)
    return df


def load_csv(uploaded_file) -> pd.DataFrame:
    return prepare_data(pd.read_csv(uploaded_file))


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
            generated_ids = pd.Series([f"{path.stem}-{sheet}-{i+1}" for i in range(len(raw))], index=raw.index)
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
        raise ValueError(f"No usable bid rows found in {path.name}")
    return prepare_data(pd.concat(frames, ignore_index=True))


def load_local_bid_data(base_dir: str | Path = ".") -> pd.DataFrame:
    base_dir = Path(base_dir)
    candidates: list[Path] = []
    candidates.extend(base_dir.glob("호수위바위*.xlsx"))
    candidates.extend(base_dir.glob("호수위바위*.xls"))
    candidates.extend(base_dir.glob("호수위바위*.csv"))
    data_dir = base_dir / "호수위바위"
    if data_dir.exists():
        candidates.extend(data_dir.glob("*.xlsx"))
        candidates.extend(data_dir.glob("*.xls"))
        candidates.extend(data_dir.glob("*.csv"))

    frames: list[pd.DataFrame] = []
    for path in sorted(set(candidates)):
        try:
            if path.suffix.lower() in [".xlsx", ".xls"]:
                frames.append(load_excel(path))
            elif path.suffix.lower() == ".csv":
                frames.append(prepare_data(pd.read_csv(path)))
        except Exception:
            continue

    if frames:
        return prepare_data(pd.concat(frames, ignore_index=True))

    sample_path = base_dir / "sample_data.csv"
    if sample_path.exists():
        return prepare_data(pd.read_csv(sample_path))
    return prepare_data(generate_sample_data())


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.rename(columns=normalize_columns(df.columns))
    if "adjustment_rate" not in df.columns and "expected_to_base_ratio" in df.columns:
        df["adjustment_rate"] = pd.to_numeric(df["expected_to_base_ratio"], errors="coerce") * 100
    if "expected_price" not in df.columns and {"base_price", "adjustment_rate"}.issubset(df.columns):
        df["expected_price"] = pd.to_numeric(df["base_price"], errors="coerce") * pd.to_numeric(df["adjustment_rate"], errors="coerce") / 100
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
    ]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["lower_rate"] = df["lower_rate"].map(normalize_rate)
    if "adjustment_rate" not in df.columns or df["adjustment_rate"].isna().all():
        df["adjustment_rate"] = df["expected_price"] / df["base_price"] * 100
    else:
        df["adjustment_rate"] = df["adjustment_rate"].fillna(df["expected_price"] / df["base_price"] * 100)

    if "minimum_bid_price" not in df.columns:
        df["minimum_bid_price"] = df["expected_price"] * df["lower_rate"] / 100
    if "opening_date" in df.columns:
        df["opening_date"] = pd.to_datetime(df["opening_date"], errors="coerce")

    return df.dropna(subset=["base_price", "expected_price", "lower_rate", "adjustment_rate"])
