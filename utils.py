from __future__ import annotations

import math
from typing import Iterable


REQUIRED_COLUMNS = ["notice_id", "title", "base_price", "expected_price", "lower_rate"]

QUANTILES = [0.10, 0.25, 0.50, 0.75, 0.90]
QUANTILE_LABELS = ["P10", "P25", "P50", "P75", "P90"]


KOREAN_COLUMN_ALIASES = {
    "공고번호": "notice_id",
    "공고명": "title",
    "발주기관": "agency",
    "지역": "region",
    "용역구분": "service_type",
    "기초금액": "base_price",
    "예정가격": "expected_price",
    "낙찰하한율": "lower_rate",
    "낙찰하한가": "minimum_bid_price",
    "낙찰금액": "winning_price",
    "투찰률": "bid_rate",
    "입찰참가자 수": "participant_count",
    "개찰일": "opening_date",
    "복수예비가격 범위": "preliminary_range",
    "사정률": "adjustment_rate",
    "낙찰 여부": "is_winner",
    "1순위 여부": "is_first_rank",
    "데이터출처": "source_url",
    "검수상태": "review_status",
}


def format_won(value: float | int | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "-"
    return f"{int(round(float(value))):,} KRW"


def format_rate(value: float | int | None, digits: int = 3) -> str:
    if value is None or not math.isfinite(float(value)):
        return "-"
    return f"{float(value):,.{digits}f}%"


def normalize_rate(rate: float) -> float:
    rate = float(rate)
    return rate * 100 if rate <= 1 else rate


def normalize_columns(columns: Iterable[str]) -> dict[str, str]:
    return {col: KOREAN_COLUMN_ALIASES.get(col, col) for col in columns}


def missing_required_columns(columns: Iterable[str]) -> list[str]:
    existing = set(columns)
    return [col for col in REQUIRED_COLUMNS if col not in existing]


def confidence_label(sample_size: int, iqr_width: float) -> tuple[str, str]:
    if sample_size < 20:
        return "High", "Similar-case sample is small, so results are volatile."
    if sample_size < 50 or iqr_width >= 1.0:
        return "Medium", "There is usable history, but conservative interpretation is needed."
    return "Low", "Similar-case sample is relatively stable."


def strategy_prices(base_price: float, lower_rate: float, q: dict[str, float]) -> dict[str, float]:
    lower_rate_ratio = normalize_rate(lower_rate) / 100
    return {
        "Conservative": base_price * (q["P75"] / 100) * lower_rate_ratio,
        "Base": base_price * (q["P50"] / 100) * lower_rate_ratio,
        "Aggressive": base_price * (q["P25"] / 100) * lower_rate_ratio,
    }
