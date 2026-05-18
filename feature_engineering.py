from __future__ import annotations

import pandas as pd


PRICE_BINS = [0, 100_000_000, 300_000_000, 700_000_000, 1_500_000_000, float("inf")]
PRICE_LABELS = ["<100M", "100M-300M", "300M-700M", "700M-1.5B", ">=1.5B"]


def add_price_band(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["price_band"] = pd.cut(df["base_price"], bins=PRICE_BINS, labels=PRICE_LABELS, include_lowest=True)
    return df


def filter_similar_cases(
    df: pd.DataFrame,
    base_price: float,
    lower_rate: float,
    agency: str | None = None,
    region: str | None = None,
    service_type: str | None = None,
    preliminary_range: str | None = None,
) -> pd.DataFrame:
    data = add_price_band(df)
    target_band = pd.cut(pd.Series([base_price]), bins=PRICE_BINS, labels=PRICE_LABELS, include_lowest=True).iloc[0]
    similar = data[
        (data["price_band"] == target_band)
        & (data["lower_rate"].round(3) == round(float(lower_rate), 3))
    ].copy()

    for col, value in [
        ("agency", agency),
        ("region", region),
        ("service_type", service_type),
        ("preliminary_range", preliminary_range),
    ]:
        if value and value != "All" and col in similar.columns:
            narrowed = similar[similar[col] == value]
            if len(narrowed) >= 10:
                similar = narrowed

    if len(similar) < 10:
        similar = data[data["lower_rate"].round(3) == round(float(lower_rate), 3)].copy()
    if len(similar) < 10:
        similar = data.copy()
    return similar


def group_statistics(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = add_price_band(df)
    by_lower_rate = (
        data.groupby("lower_rate", observed=True)["adjustment_rate"]
        .agg(["count", "mean", "median", "std"])
        .reset_index()
    )
    by_band_rate = (
        data.groupby(["price_band", "lower_rate"], observed=True)["adjustment_rate"]
        .agg(["count", "mean", "median", "std"])
        .reset_index()
    )
    return by_lower_rate, by_band_rate
