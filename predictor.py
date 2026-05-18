from __future__ import annotations

import numpy as np
import pandas as pd

from feature_engineering import filter_similar_cases
from utils import QUANTILE_LABELS, QUANTILES, confidence_label, normalize_rate, strategy_prices


class DistributionPredictor:
    def __init__(self, min_samples: int = 30):
        self.min_samples = min_samples
        self.df: pd.DataFrame | None = None

    def fit(self, df: pd.DataFrame) -> "DistributionPredictor":
        self.df = df.copy()
        return self

    def predict(
        self,
        base_price: float,
        lower_rate: float,
        agency: str | None = None,
        region: str | None = None,
        service_type: str | None = None,
        preliminary_range: str | None = None,
    ) -> dict:
        if self.df is None:
            raise RuntimeError("Call fit(df) before predict().")

        lower_rate = normalize_rate(lower_rate)
        similar = filter_similar_cases(
            self.df,
            base_price=base_price,
            lower_rate=lower_rate,
            agency=agency,
            region=region,
            service_type=service_type,
            preliminary_range=preliminary_range,
        )
        rates = similar["adjustment_rate"].dropna()
        quantile_values = rates.quantile(QUANTILES).to_dict()
        q = {label: float(quantile_values[quantile]) for label, quantile in zip(QUANTILE_LABELS, QUANTILES)}

        expected_prices = {label: base_price * rate / 100 for label, rate in q.items()}
        min_bid_prices = {label: price * lower_rate / 100 for label, price in expected_prices.items()}
        iqr_width = q["P75"] - q["P25"]
        risk, risk_message = confidence_label(len(similar), iqr_width)

        return {
            "mean_rate": float(rates.mean()),
            "median_rate": float(rates.median()),
            "quantiles": q,
            "expected_prices": expected_prices,
            "min_bid_prices": min_bid_prices,
            "strategy_prices": strategy_prices(base_price, lower_rate, q),
            "similar_cases": similar.sort_values("opening_date", ascending=False)
            if "opening_date" in similar.columns
            else similar,
            "sample_size": int(len(similar)),
            "risk_level": risk,
            "risk_message": risk_message,
        }


def weighted_quantiles(values: np.ndarray, weights: np.ndarray, quantiles: list[float]) -> np.ndarray:
    sorter = np.argsort(values)
    values = values[sorter]
    weights = weights[sorter]
    cumulative = np.cumsum(weights)
    cumulative = cumulative / cumulative[-1]
    return np.interp(quantiles, cumulative, values)


def apply_market_adjustment(
    result: dict,
    base_price: float,
    lower_rate: float,
    enabled: bool = False,
    weight: float = 0.35,
    low_mode: float = 99.5,
    high_mode: float = 100.4,
    low_share: float = 0.5,
) -> dict:
    if not enabled:
        return result

    lower_rate = normalize_rate(lower_rate)
    weight = float(np.clip(weight, 0.0, 0.8))
    low_share = float(np.clip(low_share, 0.0, 1.0))

    market_rates = np.array(
        [
            low_mode - 0.18,
            low_mode - 0.05,
            low_mode + 0.05,
            high_mode - 0.05,
            high_mode + 0.05,
            high_mode + 0.18,
        ]
    )
    market_weights = np.array(
        [
            low_share * 0.25,
            low_share * 0.50,
            low_share * 0.25,
            (1 - low_share) * 0.25,
            (1 - low_share) * 0.50,
            (1 - low_share) * 0.25,
        ]
    )
    market_quantiles = weighted_quantiles(market_rates, market_weights, QUANTILES)

    adjusted = result.copy()
    adjusted_q = {}
    for label, market_rate in zip(QUANTILE_LABELS, market_quantiles):
        adjusted_q[label] = float((1 - weight) * result["quantiles"][label] + weight * market_rate)

    adjusted["quantiles"] = adjusted_q
    adjusted["mean_rate"] = float((1 - weight) * result["mean_rate"] + weight * np.average(market_rates, weights=market_weights))
    adjusted["median_rate"] = adjusted_q["P50"]
    adjusted["expected_prices"] = {label: base_price * rate / 100 for label, rate in adjusted_q.items()}
    adjusted["min_bid_prices"] = {label: price * lower_rate / 100 for label, price in adjusted["expected_prices"].items()}
    adjusted["strategy_prices"] = strategy_prices(base_price, lower_rate, adjusted_q)
    adjusted["market_adjustment"] = {
        "enabled": True,
        "weight": weight,
        "low_mode": low_mode,
        "high_mode": high_mode,
        "low_share": low_share,
    }
    return adjusted


def simulate_preliminary_price_draws(
    range_percent: float = 3.0,
    n_preliminary_prices: int = 15,
    n_draws: int = 4,
    n_trials: int = 50_000,
    seed: int | None = 42,
) -> dict:
    rng = np.random.default_rng(seed)
    preliminary_rates = rng.uniform(100 - range_percent, 100 + range_percent, size=(n_trials, n_preliminary_prices))
    random_order = rng.random(size=(n_trials, n_preliminary_prices)).argsort(axis=1)
    picked = np.take_along_axis(preliminary_rates, random_order[:, :n_draws], axis=1)
    adjustment_rates = picked.mean(axis=1)
    qs = np.quantile(adjustment_rates, QUANTILES)
    return {
        "mean_rate": float(adjustment_rates.mean()),
        "median_rate": float(np.median(adjustment_rates)),
        "quantiles": {label: float(value) for label, value in zip(QUANTILE_LABELS, qs)},
        "range_percent": range_percent,
    }


def simulate_single_preliminary_draw(
    range_percent: float = 3.0,
    n_preliminary_prices: int = 15,
    n_draws: int = 4,
    seed: int | None = None,
) -> dict:
    rng = np.random.default_rng(seed)
    preliminary_rates = rng.uniform(100 - range_percent, 100 + range_percent, size=n_preliminary_prices)
    picked_indexes = rng.choice(np.arange(n_preliminary_prices), size=n_draws, replace=False)
    picked_rates = preliminary_rates[picked_indexes]
    return {
        "preliminary_rates": [float(v) for v in preliminary_rates],
        "picked_indexes": [int(i) + 1 for i in picked_indexes],
        "picked_rates": [float(v) for v in picked_rates],
        "adjustment_rate": float(picked_rates.mean()),
    }


def simulate_competitive_bidding(
    base_price: float,
    lower_rate: float,
    participant_count: int = 150,
    range_percent: float = 3.0,
    bidder_rate_mean: float = 100.0,
    bidder_rate_std: float = 0.65,
    seed: int | None = None,
) -> dict:
    rng = np.random.default_rng(seed)
    lower_rate = normalize_rate(lower_rate)
    participant_count = int(max(1, participant_count))

    preliminary_rates = rng.uniform(100 - range_percent, 100 + range_percent, size=15)
    picked_number_counts = np.zeros(15, dtype=int)
    for _ in range(participant_count):
        picked_numbers = rng.choice(np.arange(15), size=2, replace=False)
        picked_number_counts[picked_numbers] += 1

    tie_breaker = rng.random(15)
    top4_indexes = np.lexsort((tie_breaker, -picked_number_counts))[:4]
    expected_adjustment_rate = float(preliminary_rates[top4_indexes].mean())
    expected_price = float(base_price * expected_adjustment_rate / 100)
    minimum_eligible_bid = float(expected_price * lower_rate / 100)

    bidder_adjustment_rates = np.clip(rng.normal(bidder_rate_mean, bidder_rate_std, size=participant_count), 97.0, 103.0)
    bid_prices = base_price * lower_rate / 100 * bidder_adjustment_rates / 100
    eligible_mask = bid_prices >= minimum_eligible_bid

    if eligible_mask.any():
        eligible_indexes = np.where(eligible_mask)[0]
        winner_index = int(eligible_indexes[np.argmin(bid_prices[eligible_mask])])
        winning_bid = float(bid_prices[winner_index])
        winning_bidder_rate = float(bidder_adjustment_rates[winner_index])
        gap_to_floor = float(winning_bid - minimum_eligible_bid)
    else:
        winner_index = None
        winning_bid = None
        winning_bidder_rate = None
        gap_to_floor = None

    bidder_table = pd.DataFrame(
        {
            "bidder_no": np.arange(1, participant_count + 1),
            "bidder_adjustment_rate": bidder_adjustment_rates,
            "bid_price": bid_prices,
            "eligible": eligible_mask,
        }
    ).sort_values(["eligible", "bid_price"], ascending=[False, True])

    return {
        "preliminary_rates": [float(v) for v in preliminary_rates],
        "picked_number_counts": [int(v) for v in picked_number_counts],
        "top4_indexes": [int(v) + 1 for v in top4_indexes],
        "top4_rates": [float(v) for v in preliminary_rates[top4_indexes]],
        "expected_adjustment_rate": expected_adjustment_rate,
        "expected_price": expected_price,
        "minimum_eligible_bid": minimum_eligible_bid,
        "participant_count": participant_count,
        "winner_index": None if winner_index is None else winner_index + 1,
        "winning_bid": winning_bid,
        "winning_bidder_rate": winning_bidder_rate,
        "gap_to_floor": gap_to_floor,
        "eligible_count": int(eligible_mask.sum()),
        "bidder_table": bidder_table,
    }
