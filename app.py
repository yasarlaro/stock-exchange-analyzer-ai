"""AlphaVision Equity Terminal — Streamlit entry point."""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from alphavision.universe import build_universe

logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="AlphaVision Equity Terminal",
    page_icon=":bar_chart:",
    layout="wide",
)

st.title("AlphaVision Equity Terminal")
st.caption("S&P 500 + Nasdaq-100 equity universe — updated on demand")


@st.cache_data(show_spinner="Fetching equity universe…")
def _load_universe() -> pd.DataFrame:
    return build_universe()


df = _load_universe()

sp500_count = int((df["source"] == "SP500").sum())
ndx100_count = int((df["source"] == "NDX100").sum())
both_count = int((df["source"] == "BOTH").sum())
total_count = len(df)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Tickers", total_count)
col2.metric("S&P 500 Only", sp500_count)
col3.metric("Nasdaq-100 Only", ndx100_count)
col4.metric("In Both Indices", both_count)

st.divider()

search = st.text_input(
    "Search by ticker or company name",
    placeholder="e.g. AAPL or Apple",
)

if search:
    mask = df["ticker"].str.contains(search, case=False, na=False) | df[
        "company"
    ].str.contains(search, case=False, na=False)
    display_df = df[mask]
else:
    display_df = df

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "ticker": st.column_config.TextColumn("Ticker", width="small"),
        "company": st.column_config.TextColumn("Company"),
        "sector": st.column_config.TextColumn("Sector"),
        "source": st.column_config.TextColumn("Index", width="small"),
    },
)

st.caption(
    f"Showing {len(display_df)} of {total_count} tickers. "
    "Data sourced from Wikipedia."
)
