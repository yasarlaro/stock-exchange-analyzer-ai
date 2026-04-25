"""AlphaVision Equity Terminal — Streamlit entry point."""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from alphavision.filters import (
    apply_dual_track,
    passes_momentum,
    passes_turnaround,
)
from alphavision.scoring import rank_candidates
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

tab_universe, tab_analysis = st.tabs(["Universe", "Analysis"])

with tab_universe:
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

with tab_analysis:
    st.subheader("Dual-Track Filter & Conviction Score")
    st.markdown(
        "Fetch live financial data for all tickers, apply the Dual-Track "
        "filter, and rank candidates by Conviction Score (0–100).\n\n"
        "> **Note**: fetching ~520 tickers may take several minutes."
    )

    if st.button("Run Scoring Analysis", type="primary"):
        from alphavision.data_fetcher import fetch_ticker

        tickers = df["ticker"].tolist()
        progress = st.progress(0, text="Fetching financial data…")
        universe_data = []
        for idx, sym in enumerate(tickers):
            try:
                universe_data.append(fetch_ticker(sym))
            except Exception:
                pass
            progress.progress(
                (idx + 1) / len(tickers),
                text=f"Fetched {idx + 1}/{len(tickers)} — {sym}",
            )
        progress.empty()

        candidates = apply_dual_track(universe_data)
        top20 = rank_candidates(candidates)

        ch_a = sum(1 for d in universe_data if passes_turnaround(d))
        ch_b = sum(1 for d in universe_data if passes_momentum(d))
        ch_both = sum(
            1
            for d in universe_data
            if passes_turnaround(d) and passes_momentum(d)
        )

        st.session_state["top20"] = top20
        st.session_state["analysis_stats"] = {
            "fetched": len(universe_data),
            "candidates": len(candidates),
            "ch_a": ch_a,
            "ch_b": ch_b,
            "ch_both": ch_both,
        }

    if "top20" in st.session_state:
        stats = st.session_state["analysis_stats"]
        top20 = st.session_state["top20"]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Tickers Fetched", stats["fetched"])
        m2.metric("Channel A (Turnaround)", stats["ch_a"])
        m3.metric("Channel B (Momentum)", stats["ch_b"])
        m4.metric("Total Candidates", stats["candidates"])

        st.divider()
        st.subheader("Top 20 — Conviction Score Ranking")

        rows = [
            {
                "Rank": s.rank,
                "Ticker": s.ticker,
                "Company": s.company,
                "Score": s.conviction_score,
                "Upside Gap": s.upside_gap_score,
                "Rating Drift": s.rating_drift_score,
                "Consensus": s.consensus_strength_score,
                "EPS Mom.": s.eps_momentum_score,
                "Channel": s.channel,
            }
            for s in top20
        ]
        top20_df = pd.DataFrame(rows)

        st.dataframe(
            top20_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rank": st.column_config.NumberColumn("Rank", width="small"),
                "Score": st.column_config.NumberColumn("Score", format="%.1f"),
                "Upside Gap": st.column_config.NumberColumn(
                    "Upside Gap", format="%.1f"
                ),
                "Rating Drift": st.column_config.NumberColumn(
                    "Rating Drift", format="%.1f"
                ),
                "Consensus": st.column_config.NumberColumn(
                    "Consensus", format="%.1f"
                ),
                "EPS Mom.": st.column_config.NumberColumn(
                    "EPS Mom.", format="%.1f"
                ),
            },
        )
    else:
        st.info(
            "Click **Run Scoring Analysis** to fetch data and score tickers."
        )
