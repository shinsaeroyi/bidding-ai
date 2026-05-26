from __future__ import annotations

from pathlib import Path
import time

import pandas as pd
import streamlit as st

from data_loader import load_local_bid_data
from predictor import DistributionPredictor, simulate_competitive_bidding
from utils import format_rate, format_won


st.set_page_config(page_title="입찰 AI 시뮬레이터", layout="wide")
st.title("입찰 AI 시뮬레이터")
st.caption("과거 데이터 기반 예정가격 범위와 참여업체 수별 단일 낙찰 결과 시뮬레이션")


def parse_range_percent(value: str) -> float:
    return 2.0 if value == "±2%" else 3.0


def load_current_data() -> pd.DataFrame:
    return load_local_bid_data(Path(__file__).parent)


try:
    df = load_current_data()
except Exception as exc:
    st.error(f"데이터를 불러오지 못했습니다: {exc}")
    st.stop()

with st.sidebar:
    st.header("데이터")
    st.metric("반영된 입찰 데이터", f"{len(df):,}건")
    if "opening_date" in df.columns and df["opening_date"].notna().any():
        st.caption(
            f"개찰일 범위: {df['opening_date'].min().date()} ~ {df['opening_date'].max().date()}"
        )
    source_files = sorted(df["source_file"].dropna().unique()) if "source_file" in df.columns else []
    if source_files:
        st.caption("반영 파일: " + ", ".join(source_files[:5]))
    st.caption("과거 데이터 파일을 저장한 뒤 브라우저에서 F5를 누르면 최신 내용이 반영됩니다.")
    if st.button("지금 데이터 다시 불러오기"):
        st.rerun()

st.subheader("입찰 조건 입력")
c1, c2, c3, c4 = st.columns(4)
base_price = c1.number_input("기초금액", min_value=1_000_000, value=250_000_000, step=1_000_000, format="%d")
lower_rate = c2.number_input("낙찰하한율(%)", min_value=60.0, max_value=100.0, value=87.745, step=0.001, format="%.3f")
preliminary_range = c3.selectbox("복수예비가격 범위", ["±3%", "±2%"], index=0)
participant_count = c4.number_input("참여 업체 수", min_value=1, max_value=1000, value=150, step=10)

c5, c6 = st.columns(2)
bidder_mean = c5.number_input("업체별 사정률 평균", min_value=95.0, max_value=105.0, value=100.0, step=0.05, format="%.3f")
bidder_std = c6.number_input("업체별 사정률 표준편차", min_value=0.05, max_value=3.0, value=0.65, step=0.05, format="%.3f")

run = st.button("시뮬레이션 실행", type="primary")
if run or "last_seed" not in st.session_state:
    st.session_state.last_seed = int(time.time() * 1000) % 2_147_483_647


predictor = DistributionPredictor().fit(df)
distribution = predictor.predict(base_price=base_price, lower_rate=lower_rate)
competition = simulate_competitive_bidding(
    base_price=base_price,
    lower_rate=lower_rate,
    participant_count=participant_count,
    range_percent=parse_range_percent(preliminary_range),
    bidder_rate_mean=bidder_mean,
    bidder_rate_std=bidder_std,
    seed=st.session_state.last_seed,
)

st.subheader("결과")
k1, k2, k3, k4 = st.columns(4)
k1.metric("시뮬레이션 예정가격", format_won(competition["expected_price"]))
k2.metric("예정가격 사정률", format_rate(competition["expected_adjustment_rate"]))
k3.metric("낙찰하한가", format_won(competition["minimum_eligible_bid"]))
k4.metric("적격 업체 수", f"{competition['eligible_count']:,}개")

if competition["winning_bid"] is None:
    st.error("이번 시뮬레이션에서는 낙찰하한가 이상 투찰 업체가 없습니다.")
else:
    st.success(
        f"낙찰자: 업체 {competition['winner_index']} / "
        f"낙찰금액 {format_won(competition['winning_bid'])} / "
        f"업체별 사정률 {format_rate(competition['winning_bidder_rate'])} / "
        f"하한가 대비 +{format_won(competition['gap_to_floor'])}"
    )

st.caption(
    "선택된 복수예비가격 번호: "
    + ", ".join([str(v) for v in sorted(competition["top4_indexes"])])
    + " / 선택된 사정률: "
    + ", ".join([format_rate(v) for v in competition["top4_rates"]])
)

st.subheader("과거 데이터 기반 사정률 분포")
q = distribution["quantiles"]
q_rows = []
for label, rate in q.items():
    expected_price = base_price * rate / 100
    min_bid = expected_price * lower_rate / 100
    q_rows.append(
        {
            "분위수": label,
            "사정률": format_rate(rate),
            "예상 예정가격": format_won(expected_price),
            "예상 낙찰하한가": format_won(min_bid),
        }
    )
st.dataframe(pd.DataFrame(q_rows), width="stretch", hide_index=True)
st.caption(
    f"현재 분포는 {len(distribution['similar_cases']):,}건 기준입니다. "
    "엑셀 파일이 추가되면 새로고침 후 이 분포에 자동 반영됩니다."
)

st.subheader("상위 투찰 결과")
bidder_table = competition["bidder_table"].head(30).copy()
bidder_table["bidder_adjustment_rate"] = bidder_table["bidder_adjustment_rate"].map(format_rate)
bidder_table["bid_price"] = bidder_table["bid_price"].map(format_won)
bidder_table = bidder_table.rename(
    columns={
        "bidder_no": "업체번호",
        "bidder_adjustment_rate": "업체별 사정률",
        "bid_price": "투찰금액",
        "eligible": "낙찰하한가 이상",
    }
)
st.dataframe(bidder_table, width="stretch", hide_index=True)

with st.expander("반영된 원천 데이터 미리보기"):
    preview_cols = [
        "title",
        "agency",
        "opening_date",
        "base_price",
        "household_count",
        "adjustment_rate",
        "source_file",
    ]
    existing_cols = [col for col in preview_cols if col in df.columns]
    st.dataframe(df[existing_cols].head(100), width="stretch", hide_index=True)
