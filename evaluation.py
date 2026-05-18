from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error


def evaluate_point_predictions(y_true: pd.Series, y_pred: pd.Series) -> dict[str, float]:
    abs_error = (y_true - y_pred).abs()
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "Median Absolute Error": float(abs_error.median()),
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
    }


def interval_hit_rate(y_true: pd.Series, lower: pd.Series, upper: pd.Series) -> float:
    return float(((y_true >= lower) & (y_true <= upper)).mean())


def evaluate_distribution(df: pd.DataFrame) -> dict[str, float]:
    q10, q25, q50, q75, q90 = df["adjustment_rate"].quantile([0.10, 0.25, 0.50, 0.75, 0.90])
    y_true = df["adjustment_rate"]
    y_pred = pd.Series(q50, index=df.index)
    metrics = evaluate_point_predictions(y_true, y_pred)
    metrics["P10-P90 hit rate"] = interval_hit_rate(y_true, pd.Series(q10, index=df.index), pd.Series(q90, index=df.index))
    metrics["P25-P75 hit rate"] = interval_hit_rate(y_true, pd.Series(q25, index=df.index), pd.Series(q75, index=df.index))
    if {"winning_price", "minimum_bid_price"}.issubset(df.columns):
        metrics["Below floor rate"] = float((df["winning_price"] < df["minimum_bid_price"]).mean())
    return metrics
