from __future__ import annotations

from pathlib import Path
import time

import pandas as pd
import streamlit as st

from data_loader import generate_sample_data, load_csv, prepare_data
from evaluation import evaluate_distribution
from feature_engineering import group_statistics
from predictor import (
    DistributionPredictor,
    apply_market_adjustment,
    simulate_competitive_bidding,
    simulate_preliminary_price_draws,
    simulate_single_preliminary_draw,
)
from ui_components import (
    apply_page_style,
    render_distribution_chart,
    render_price_range_chart,
    render_quantile_table,
    render_result_cards,
    render_strategy,
)
from utils import REQUIRED_COLUMNS, format_rate, format_won


apply_page_style()
st.title("Bidding AI Simulator")
st.caption("Expected-price range, minimum eligible bid, and competitive bidding simulation for Korean supervision-service bids.")


@st.cache_data
def get_sample_data() -> pd.DataFrame:
    sample_path = Path(__file__).with_name("sample_data.csv")
    if sample_path.exists():
        return prepare_data(pd.read_csv(sample_path))
    return prepare_data(generate_sample_data())


if "bid_data" not in st.session_state:
    st.session_state.bid_data = get_sample_data()
    st.session_state.data_source_label = "sample"
if "simulation_seed" not in st.session_state:
    st.session_state.simulation_seed = int(time.time())
if "competitive_seed" not in st.session_state:
    st.session_state.competitive_seed = int(time.time() * 1000) % 2_147_483_647


def select_optional(label: str, df: pd.DataFrame, column: str) -> str:
    if column not in df.columns:
        return "All"
    values = ["All"] + sorted([str(v) for v in df[column].dropna().unique()])
    return st.selectbox(label, values)


def parse_range_percent(value: str) -> float:
    if value == "+/-2%":
        return 2.0
    return 3.0


tabs = st.tabs(["Dashboard", "Data Upload", "Prediction", "Similar Cases", "Model Evaluation", "Settings"])
df = st.session_state.bid_data

with tabs[0]:
    st.subheader("Dashboard")
    st.warning("The included CSV is a small public-web sample. Verify original notices before using it for real bidding.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", f"{len(df):,}")
    c2.metric("Mean adjustment", format_rate(df["adjustment_rate"].mean()))
    c3.metric("Median adjustment", format_rate(df["adjustment_rate"].median()))
    c4.metric("Median base price", format_won(df["base_price"].median()))

    by_lower_rate, by_band_rate = group_statistics(df)
    st.write("By lower-rate")
    st.dataframe(by_lower_rate.round(3), width="stretch", hide_index=True)
    st.write("By base-price band and lower-rate")
    st.dataframe(by_band_rate.round(3), width="stretch", hide_index=True)

with tabs[1]:
    st.subheader("Data Upload")
    st.write("Required columns: " + ", ".join(REQUIRED_COLUMNS))
    st.write("Korean column names such as 공고번호, 공고명, 기초금액, 예정가격, 낙찰하한율 are also accepted.")
    uploaded = st.file_uploader("Upload historical bid CSV", type=["csv"])
    col_a, col_b = st.columns([1, 1])
    if uploaded:
        try:
            st.session_state.bid_data = load_csv(uploaded)
            st.session_state.data_source_label = "uploaded"
            st.success(f"Loaded {len(st.session_state.bid_data):,} rows.")
        except Exception as exc:
            st.error(str(exc))
    with col_a:
        if st.button("Reset to sample data"):
            st.session_state.bid_data = get_sample_data()
            st.session_state.data_source_label = "sample"
            st.success("Sample data loaded.")
    with col_b:
        st.download_button(
            "Download sample CSV",
            data=get_sample_data().to_csv(index=False).encode("utf-8-sig"),
            file_name="sample_data.csv",
            mime="text/csv",
        )
    st.dataframe(st.session_state.bid_data.head(30), width="stretch")

with tabs[2]:
    st.subheader("Prediction")
    df = st.session_state.bid_data
    with st.form("prediction_form"):
        c1, c2, c3 = st.columns(3)
        base_price = c1.number_input("Base price", min_value=1_000_000, value=250_000_000, step=1_000_000, format="%d")
        lower_rate = c2.number_input("Lower-rate (%)", min_value=70.0, max_value=100.0, value=87.745, step=0.001, format="%.3f")
        preliminary_range = c3.selectbox("Preliminary price range", ["+/-3%", "+/-2%"])
        c4, c5, c6 = st.columns(3)
        agency = select_optional("Agency", df, "agency")
        region = select_optional("Region", df, "region")
        service_type = select_optional("Service type", df, "service_type")

        st.write("Market adjustment")
        market_adjustment = st.checkbox("Apply recent market view", value=True)
        m1, m2, m3 = st.columns(3)
        low_mode = m1.number_input("Lower frequent rate", value=99.500, step=0.050, format="%.3f")
        high_mode = m2.number_input("Upper frequent rate", value=100.400, step=0.050, format="%.3f")
        adjustment_weight = m3.slider("Adjustment weight", min_value=0.0, max_value=0.8, value=0.35, step=0.05)
        low_share = st.slider("Lower-mode share", min_value=0.0, max_value=1.0, value=0.5, step=0.05)
        submitted = st.form_submit_button("Run prediction", type="primary")

    if submitted:
        predictor = DistributionPredictor().fit(df)
        result = predictor.predict(
            base_price=base_price,
            lower_rate=lower_rate,
            agency=agency,
            region=region,
            service_type=service_type,
            preliminary_range=preliminary_range,
        )
        result = apply_market_adjustment(
            result,
            base_price=base_price,
            lower_rate=lower_rate,
            enabled=market_adjustment,
            weight=adjustment_weight,
            low_mode=low_mode,
            high_mode=high_mode,
            low_share=low_share,
        )
        st.session_state.last_result = result
        st.session_state.last_input = {"base_price": base_price, "lower_rate": lower_rate, "preliminary_range": preliminary_range}

    result = st.session_state.get("last_result")
    if result:
        if result["sample_size"] < 30:
            st.warning("Fewer than 30 similar cases are available. Treat this as a reference only.")
        render_result_cards(result)
        if result.get("market_adjustment", {}).get("enabled"):
            ma = result["market_adjustment"]
            st.info(
                f"Market adjustment applied: {ma['low_mode']:.3f}% / {ma['high_mode']:.3f}% "
                f"with {ma['weight'] * 100:.0f}% weight."
            )
        render_quantile_table(result)
        selected_strategy = st.radio("Strategy", ["Conservative", "Base", "Aggressive"], index=1, horizontal=True, key="selected_strategy")
        render_strategy(result, selected_strategy)

        last_input = st.session_state.last_input
        with st.expander("Single competitive bidding simulation", expanded=True):
            st.caption(
                "Generates 15 preliminary prices, lets each participant pick 2 numbers, uses the 4 most selected numbers "
                "to set the expected price, then selects the lowest bid above the minimum eligible bid."
            )
            s1, s2, s3 = st.columns(3)
            participant_count = s1.number_input("Participant count", min_value=1, max_value=1000, value=150, step=10)
            bidder_mean = s2.number_input("Bidder adjustment mean", min_value=95.0, max_value=105.0, value=100.0, step=0.05, format="%.3f")
            bidder_std = s3.number_input("Bidder adjustment std", min_value=0.05, max_value=3.0, value=0.65, step=0.05, format="%.3f")
            if st.button("Run competitive simulation again"):
                st.session_state.competitive_seed = int(time.time() * 1000) % 2_147_483_647
                st.rerun()
            competition = simulate_competitive_bidding(
                base_price=last_input["base_price"],
                lower_rate=last_input["lower_rate"],
                participant_count=participant_count,
                range_percent=parse_range_percent(last_input["preliminary_range"]),
                bidder_rate_mean=bidder_mean,
                bidder_rate_std=bidder_std,
                seed=st.session_state.competitive_seed,
            )
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Simulated expected price", format_won(competition["expected_price"]))
            k2.metric("Expected adjustment", format_rate(competition["expected_adjustment_rate"]))
            k3.metric("Minimum eligible bid", format_won(competition["minimum_eligible_bid"]))
            k4.metric("Eligible bidders", f"{competition['eligible_count']:,}")
            if competition["winning_bid"] is None:
                st.error("No bidder met the minimum eligible bid in this run.")
            else:
                st.success(
                    f"Winner bidder #{competition['winner_index']} | Winning bid {format_won(competition['winning_bid'])} | "
                    f"Bidder adjustment {format_rate(competition['winning_bidder_rate'])} | "
                    f"Gap above floor {format_won(competition['gap_to_floor'])}"
                )
            st.caption(
                "Selected preliminary numbers: "
                + ", ".join([str(v) for v in sorted(competition["top4_indexes"])])
                + " / rates: "
                + ", ".join([format_rate(v) for v in competition["top4_rates"]])
            )
            display_bidders = competition["bidder_table"].head(20).copy()
            display_bidders["bidder_adjustment_rate"] = display_bidders["bidder_adjustment_rate"].map(format_rate)
            display_bidders["bid_price"] = display_bidders["bid_price"].map(format_won)
            st.dataframe(display_bidders, width="stretch", hide_index=True)

        with st.expander("15 preliminary prices / 4 selected simulation", expanded=False):
            if st.button("Run preliminary simulation again"):
                st.session_state.simulation_seed = int(time.time() * 1000) % 2_147_483_647
                st.rerun()
            range_percent = parse_range_percent(preliminary_range)
            simulated = simulate_preliminary_price_draws(range_percent, seed=st.session_state.simulation_seed)
            single_draw = simulate_single_preliminary_draw(range_percent, seed=st.session_state.simulation_seed + 17)
            st.metric("Single draw adjustment", format_rate(single_draw["adjustment_rate"]))
            st.caption(
                "Picked numbers: "
                + ", ".join([str(v) for v in sorted(single_draw["picked_indexes"])])
                + " / picked rates: "
                + ", ".join([format_rate(v) for v in single_draw["picked_rates"]])
            )
            rows = []
            for label, rate in simulated["quantiles"].items():
                expected_price = base_price * rate / 100
                min_bid_price = expected_price * lower_rate / 100
                rows.append(
                    {
                        "Quantile": label,
                        "Simulated adjustment": format_rate(rate),
                        "Simulated expected price": format_won(expected_price),
                        "Simulated minimum bid": format_won(min_bid_price),
                    }
                )
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        c1, c2 = st.columns(2)
        with c1:
            render_distribution_chart(result)
        with c2:
            render_price_range_chart(result)

with tabs[3]:
    st.subheader("Similar Cases")
    result = st.session_state.get("last_result")
    if not result:
        st.info("Run prediction first.")
    else:
        columns = [
            "notice_id",
            "title",
            "agency",
            "region",
            "service_type",
            "base_price",
            "expected_price",
            "lower_rate",
            "adjustment_rate",
            "opening_date",
        ]
        available = [col for col in columns if col in result["similar_cases"].columns]
        st.dataframe(result["similar_cases"][available].head(100), width="stretch", hide_index=True)

with tabs[4]:
    st.subheader("Model Evaluation")
    metrics = evaluate_distribution(st.session_state.bid_data)
    c1, c2, c3 = st.columns(3)
    c1.metric("MAE (%p)", f"{metrics['MAE']:.3f}")
    c2.metric("Median AE (%p)", f"{metrics['Median Absolute Error']:.3f}")
    c3.metric("RMSE (%p)", f"{metrics['RMSE']:.3f}")
    c4, c5 = st.columns(2)
    c4.metric("P10-P90 hit rate", f"{metrics['P10-P90 hit rate'] * 100:.1f}%")
    c5.metric("P25-P75 hit rate", f"{metrics['P25-P75 hit rate'] * 100:.1f}%")

with tabs[5]:
    st.subheader("Settings")
    st.info("This app is a simulator and decision-support tool. It does not guarantee winning bids.")
