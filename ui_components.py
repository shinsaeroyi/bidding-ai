from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils import format_rate, format_won


def apply_page_style() -> None:
    st.set_page_config(page_title="Bidding AI Simulator", layout="wide")
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.4rem;}
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e3e8ef;
            border-radius: 8px;
            padding: 14px 16px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_result_cards(result: dict) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mean adjustment rate", format_rate(result["mean_rate"]))
    c2.metric("Median adjustment rate", format_rate(result["median_rate"]))
    c3.metric("Similar cases", f"{result['sample_size']:,}")
    c4.metric("Risk", result["risk_level"])

    q = result["quantiles"]
    st.caption(f"Historical range: {format_rate(q['P10'])} to {format_rate(q['P90'])} based on similar cases.")


def render_quantile_table(result: dict) -> None:
    rows = []
    for label, rate in result["quantiles"].items():
        rows.append(
            {
                "Quantile": label,
                "Adjustment rate": format_rate(rate),
                "Expected price": format_won(result["expected_prices"][label]),
                "Minimum eligible bid": format_won(result["min_bid_prices"][label]),
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def render_distribution_chart(result: dict) -> None:
    similar = result["similar_cases"]
    fig = px.histogram(similar, x="adjustment_rate", nbins=30, title="Adjustment-rate distribution")
    for label, rate in result["quantiles"].items():
        if label in ["P10", "P50", "P90"]:
            fig.add_vline(x=rate, line_dash="dash", annotation_text=label)
    fig.update_layout(xaxis_title="Adjustment rate (%)", yaxis_title="Count", bargap=0.08)
    st.plotly_chart(fig, width="stretch")


def render_price_range_chart(result: dict) -> None:
    labels = ["P10", "P50", "P90"]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=labels,
            y=[result["expected_prices"][label] for label in labels],
            name="Expected price",
            marker_color="#3c6e71",
        )
    )
    fig.add_trace(
        go.Bar(
            x=labels,
            y=[result["min_bid_prices"][label] for label in labels],
            name="Minimum eligible bid",
            marker_color="#d9a441",
        )
    )
    fig.update_layout(title="Expected price and floor range", yaxis_title="KRW", barmode="group")
    st.plotly_chart(fig, width="stretch")


def render_strategy(result: dict, selected_strategy: str = "Base") -> None:
    st.subheader("Bid strategy")
    c1, c2, c3 = st.columns(3)
    values = result["strategy_prices"]
    c1.metric("Conservative", format_won(values["Conservative"]))
    c2.metric("Base", format_won(values["Base"]))
    c3.metric("Aggressive", format_won(values["Aggressive"]))

    basis = {"Conservative": "P75", "Base": "P50", "Aggressive": "P25"}[selected_strategy]
    st.metric(f"Selected strategy: {selected_strategy}", format_won(values[selected_strategy]))
    st.info(f"{selected_strategy} uses {basis}. This is a reference line, not a guaranteed winning bid.")
