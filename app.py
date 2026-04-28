"""AlphaVision Equity Terminal — Streamlit entry point."""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from alphavision.filters import apply_forward_momentum
from alphavision.scoring import rank_candidates
from alphavision.ticker_utils import (
    parse_ticker_input,
    validate_against_universe,
)
from alphavision.universe import build_universe

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

tab_universe, tab_analysis, tab_custom = st.tabs(
    ["Universe", "Analysis", "Custom Analysis"]
)

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
    st.subheader("Forward-Momentum Filter & Conviction Score (v3.0)")
    st.markdown(
        "Fetch live financial data for all tickers, apply the "
        "Forward-Momentum gate, and rank survivors by Conviction Score "
        "(0–100).\n\n"
        "**Conviction Score v3.0 weights**: Relative Strength (12-1) 30% "
        "· EPS Revision 25% · Rating Drift 15% · Trend Quality 15% · "
        "Upside Gap 10% · Consensus 5%\n\n"
        "**Stress test**: tickers stretched >10% above the 20-day SMA "
        "have their score dampened by 10%.\n\n"
        "> **Data sources**: prices via yfinance · "
        "analyst ratings & targets via Finnhub (primary) / yfinance "
        "(fallback — set `FINNHUB_API_KEY` in `.env` for full signals) · "
        "fundamentals via SEC EDGAR (primary) / yfinance (fallback — "
        "set `EDGAR_IDENTITY` in `.env` for better rate limits)\n\n"
        "> **Two-phase analysis**: ~520 tickers batch price-fetched first "
        "(seconds), then analyst + fundamentals fetched only for the "
        "~35–45% that pass the price gate — expect **7–10 minutes** on "
        "the free Finnhub tier."
    )

    # ── Phase 1: trigger pre-flight ────────────────────────────────────────
    if st.button("Run Analysis", type="primary"):
        st.session_state["analysis_phase"] = "preflight"
        # Clear previous results when starting a new run.
        for key in ("top20", "analysis_stats", "provider_status"):
            st.session_state.pop(key, None)

    # ── Phase 2: pre-flight check ──────────────────────────────────────────
    if st.session_state.get("analysis_phase") == "preflight":
        from alphavision.data_fetcher import probe_providers

        status = probe_providers()
        st.session_state["provider_status"] = status
        st.session_state["analysis_phase"] = "confirm"
        st.rerun()

    # ── Phase 3: provider status + confirm ─────────────────────────────────
    if st.session_state.get("analysis_phase") == "confirm":
        status = st.session_state["provider_status"]

        st.markdown("#### Data Provider Status")
        p_col, a_col, f_col = st.columns(3)
        p_col.metric(
            "Prices",
            "yfinance",
            delta="primary",
            delta_color="normal",
        )
        analyst_label = (
            "Finnhub" if status.finnhub_key_set else "yfinance (fallback)"
        )
        analyst_delta = "primary" if status.finnhub_key_set else "degraded"
        a_col.metric(
            "Analyst Signals",
            analyst_label,
            delta=analyst_delta,
            delta_color="normal" if status.finnhub_key_set else "inverse",
        )
        edgar_label = (
            "EDGAR (custom ID)"
            if status.edgar_identity_custom
            else "EDGAR (default ID)"
        )
        f_col.metric(
            "Fundamentals",
            edgar_label,
            delta="primary" if status.edgar_identity_custom else "generic",
            delta_color=("normal" if status.edgar_identity_custom else "off"),
        )

        if status.warnings:
            for warn in status.warnings:
                st.warning(warn)
        else:
            st.success(
                "All providers fully configured. Full-accuracy analysis."
            )

        st.markdown(
            "**Signal degradation detail** (when running without "
            "full provider configuration):\n"
            "- No Finnhub key → Rating Drift and Consensus sub-scores "
            "use yfinance data (less frequent updates, fewer data points).\n"
            "- Default EDGAR identity → SEC rate limits may be tighter; "
            "no impact on data quality.\n"
            "- All degraded modes still produce scored results — "
            "scores will be weighted toward RS and EPS Revision signals."
        )

        st.divider()
        c_continue, c_cancel = st.columns([1, 4])
        if c_continue.button("Continue with available data", type="primary"):
            st.session_state["analysis_phase"] = "running"
            st.rerun()
        if c_cancel.button("Cancel"):
            st.session_state["analysis_phase"] = None
            st.rerun()

    # ── Phase 4: run full analysis ─────────────────────────────────────────
    if st.session_state.get("analysis_phase") == "running":
        from alphavision.data_fetcher import fetch_universe_two_phase

        tickers = df["ticker"].tolist()
        company_lookup = dict(zip(df["ticker"], df["company"]))
        logger.info("Analysis started: %d tickers in universe.", len(tickers))

        with st.status(
            f"Phase 1: batch price-fetching {len(tickers)} tickers…",
            expanded=True,
        ) as status_widget:
            progress_placeholder = st.empty()

            def _ui_status(msg: str) -> None:
                progress_placeholder.write(msg)

            universe_data, total_scanned = fetch_universe_two_phase(
                tickers,
                company_lookup=company_lookup,
                status_fn=_ui_status,
            )

            price_gate_n = len(universe_data)
            status_widget.update(
                label=(
                    f"{price_gate_n} passed price gate. "
                    "Applying full Forward-Momentum gate…"
                )
            )
            _ui_status(
                f"Applying full Forward-Momentum gate to "
                f"{price_gate_n} tickers…"
            )

            candidates = apply_forward_momentum(universe_data)
            passing = len(candidates)
            logger.info(
                "Filter result: %d of %d passed full gate.",
                passing,
                price_gate_n,
            )

            _ui_status(
                f"Full gate passed: {passing} of {price_gate_n}. "
                "Scoring and ranking…"
            )
            top20 = rank_candidates(candidates)
            logger.info("Scoring complete: top %d ranked.", len(top20))

            over_extended_top = sum(1 for s in top20 if s.over_extended)
            status_widget.update(
                label=(
                    f"Done — {total_scanned} scanned · "
                    f"{price_gate_n} passed price gate · "
                    f"{passing} passed full gate · "
                    f"{len(top20)} ranked"
                ),
                state="complete",
            )

        st.session_state["top20"] = top20
        st.session_state["analysis_stats"] = {
            "scanned": total_scanned,
            "price_gate": price_gate_n,
            "fetched": price_gate_n,
            "passing": passing,
            "candidates": len(candidates),
            "over_extended_top": over_extended_top,
        }
        st.session_state["analysis_phase"] = "done"
        st.rerun()

    # ── Phase 5: display results ───────────────────────────────────────────
    if "top20" in st.session_state:
        stats = st.session_state["analysis_stats"]
        top20 = st.session_state["top20"]
        pstatus = st.session_state.get("provider_status")

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Universe Scanned", stats["scanned"])
        m2.metric("Passed Price Gate", stats["price_gate"])
        m3.metric("Passed Full Gate", stats["passing"])
        m4.metric("Top 20 Ranked", len(top20))
        m5.metric("Over-Extended", stats["over_extended_top"])

        if pstatus and pstatus.warnings:
            with st.expander("Data quality notices", expanded=False):
                for warn in pstatus.warnings:
                    st.caption(f"⚠ {warn}")

        st.divider()

        if not top20:
            st.warning(
                "No tickers passed the Forward-Momentum gate. "
                "Possible causes: market data unavailable, all tickers "
                "below SMA-200, or no positive 12-1 month return in "
                "the current market regime. Check logs for details."
            )
        else:
            passed_pct = (
                stats["passing"] / stats["scanned"] * 100
                if stats["scanned"]
                else 0.0
            )
            analyst_src = (
                pstatus.analyst_source.capitalize()
                if pstatus
                else "Finnhub/yfinance"
            )
            st.subheader(f"Top {len(top20)} — Conviction Score Ranking (v3.0)")
            st.caption(
                f"{stats['scanned']} scanned · "
                f"{stats['price_gate']} passed price gate · "
                f"{stats['passing']} passed full gate "
                f"({passed_pct:.1f}%) · "
                f"{stats['over_extended_top']} of top {len(top20)} "
                f"over-extended (score ×0.90) · "
                f"analyst source: {analyst_src}"
            )

            rows = [
                {
                    "Rank": s.rank,
                    "Ticker": s.ticker,
                    "Company": s.company,
                    "Score": s.conviction_score,
                    "RS (12-1)": s.relative_strength_score,
                    "EPS Rev.": s.eps_revision_score,
                    "Rating Drift": s.rating_drift_score,
                    "Trend Q.": s.trend_quality_score,
                    "Upside Gap": s.upside_gap_score,
                    "Consensus": s.consensus_strength_score,
                    "Ext. %": s.extension_pct * 100.0,
                    "Stretched": "⚠" if s.over_extended else "",
                    "Rule of 40": s.rule_of_40,
                    "Earn. Quality": s.earnings_quality,
                }
                for s in top20
            ]
            top20_df = pd.DataFrame(rows)

            st.dataframe(
                top20_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Rank": st.column_config.NumberColumn(
                        "Rank", width="small"
                    ),
                    "Score": st.column_config.NumberColumn(
                        "Score", format="%.1f"
                    ),
                    "RS (12-1)": st.column_config.NumberColumn(
                        "RS (12-1)", format="%.1f"
                    ),
                    "EPS Rev.": st.column_config.NumberColumn(
                        "EPS Rev.", format="%.1f"
                    ),
                    "Rating Drift": st.column_config.NumberColumn(
                        "Rating Drift", format="%.1f"
                    ),
                    "Trend Q.": st.column_config.NumberColumn(
                        "Trend Q.", format="%.1f"
                    ),
                    "Upside Gap": st.column_config.NumberColumn(
                        "Upside Gap", format="%.1f"
                    ),
                    "Consensus": st.column_config.NumberColumn(
                        "Consensus", format="%.1f"
                    ),
                    "Ext. %": st.column_config.NumberColumn(
                        "Ext. %", format="%.2f"
                    ),
                    "Rule of 40": st.column_config.NumberColumn(
                        "Rule of 40", format="%.1f"
                    ),
                    "Earn. Quality": st.column_config.NumberColumn(
                        "Earn. Quality", format="%.2f"
                    ),
                },
            )

        if st.button("Run New Analysis"):
            for key in (
                "top20",
                "analysis_stats",
                "analysis_phase",
                "provider_status",
            ):
                st.session_state.pop(key, None)
            st.rerun()

    elif st.session_state.get("analysis_phase") not in (
        "preflight",
        "confirm",
        "running",
    ):
        st.info("Click **Run Analysis** to fetch live data and score tickers.")

with tab_custom:
    st.subheader("Custom Ticker Analysis")
    st.markdown(
        "Enter up to 50 ticker symbols (comma, space, semicolon, or "
        "newline separated).  Each ticker is fetched live, passed through "
        "the Forward-Momentum gate, and ranked by Conviction Score.\n\n"
        "Tickers not in the S&P 500 / Nasdaq-100 universe are still "
        "analysed — the universe check is informational only."
    )

    raw_input = st.text_area(
        "Ticker symbols",
        placeholder="e.g. AAPL, MSFT, NVDA\nor one per line",
        height=120,
        key="custom_ticker_input",
    )

    tickers_parsed: list[str] = parse_ticker_input(raw_input or "")

    if tickers_parsed:
        in_uni, out_uni = validate_against_universe(tickers_parsed, df)
        col_a, col_b = st.columns(2)
        col_a.metric("Tickers Parsed", len(tickers_parsed))
        col_b.metric("In Universe", len(in_uni))
        if out_uni:
            st.caption(
                f"Not in S&P 500 / Nasdaq-100 universe "
                f"(still analysed): {', '.join(out_uni)}"
            )

    # ── Phase 1: trigger pre-flight ────────────────────────────────────────
    run_disabled = not tickers_parsed
    if st.button(
        "Run Custom Analysis",
        type="primary",
        disabled=run_disabled,
        key="custom_run_btn",
    ):
        st.session_state["custom_phase"] = "preflight"
        st.session_state["custom_tickers"] = tickers_parsed
        for key in ("custom_top", "custom_stats", "custom_provider_status"):
            st.session_state.pop(key, None)

    if not tickers_parsed and not st.session_state.get("custom_phase"):
        st.info("Enter at least one ticker symbol above to begin.")

    # ── Phase 2: pre-flight check ──────────────────────────────────────────
    if st.session_state.get("custom_phase") == "preflight":
        from alphavision.data_fetcher import probe_providers

        cstatus = probe_providers()
        st.session_state["custom_provider_status"] = cstatus
        st.session_state["custom_phase"] = "confirm"
        st.rerun()

    # ── Phase 3: provider status + confirm ─────────────────────────────────
    if st.session_state.get("custom_phase") == "confirm":
        cstatus = st.session_state["custom_provider_status"]

        st.markdown("#### Data Provider Status")
        cp_col, ca_col, cf_col = st.columns(3)
        cp_col.metric(
            "Prices", "yfinance", delta="primary", delta_color="normal"
        )
        c_analyst_label = (
            "Finnhub" if cstatus.finnhub_key_set else "yfinance (fallback)"
        )
        c_analyst_delta = "primary" if cstatus.finnhub_key_set else "degraded"
        ca_col.metric(
            "Analyst Signals",
            c_analyst_label,
            delta=c_analyst_delta,
            delta_color="normal" if cstatus.finnhub_key_set else "inverse",
        )
        c_edgar_label = (
            "EDGAR (custom ID)"
            if cstatus.edgar_identity_custom
            else "EDGAR (default ID)"
        )
        cf_col.metric(
            "Fundamentals",
            c_edgar_label,
            delta="primary" if cstatus.edgar_identity_custom else "generic",
            delta_color="normal" if cstatus.edgar_identity_custom else "off",
        )

        if cstatus.warnings:
            for warn in cstatus.warnings:
                st.warning(warn)
        else:
            st.success("All providers fully configured.")

        st.divider()
        cc_continue, cc_cancel = st.columns([1, 4])
        if cc_continue.button(
            "Continue with available data",
            type="primary",
            key="custom_continue_btn",
        ):
            st.session_state["custom_phase"] = "running"
            st.rerun()
        if cc_cancel.button("Cancel", key="custom_cancel_btn"):
            st.session_state["custom_phase"] = None
            st.rerun()

    # ── Phase 4: run analysis ──────────────────────────────────────────────
    if st.session_state.get("custom_phase") == "running":
        from alphavision.data_fetcher import fetch_universe

        ctickers = st.session_state.get("custom_tickers", [])
        logger.info("Custom analysis started: %d tickers.", len(ctickers))

        with st.status(
            f"Fetching {len(ctickers)} tickers…", expanded=True
        ) as c_status_widget:
            c_progress = st.empty()

            def _custom_ui_status(msg: str) -> None:
                c_progress.write(msg)

            custom_data = fetch_universe(ctickers, status_fn=_custom_ui_status)

            c_fetched = len(custom_data)
            c_status_widget.update(
                label=f"Fetched {c_fetched} tickers. Applying filter…"
            )
            _custom_ui_status(
                f"Applying Forward-Momentum gate to {c_fetched} tickers…"
            )

            from alphavision.filters import apply_forward_momentum

            c_candidates = apply_forward_momentum(custom_data)
            c_passing = len(c_candidates)
            logger.info(
                "Custom filter result: %d of %d passed.",
                c_passing,
                c_fetched,
            )

            _custom_ui_status(
                f"Gate passed: {c_passing} of {c_fetched}. Scoring…"
            )
            c_top = rank_candidates(c_candidates, top_n=None)
            logger.info("Custom scoring complete: %d ranked.", len(c_top))

            c_over_ext = sum(1 for s in c_top if s.over_extended)
            c_status_widget.update(
                label=(
                    f"Done — {c_fetched} fetched · {c_passing} passed "
                    f"· {len(c_top)} ranked"
                ),
                state="complete",
            )

        st.session_state["custom_top"] = c_top
        st.session_state["custom_stats"] = {
            "fetched": c_fetched,
            "passing": c_passing,
            "over_extended": c_over_ext,
        }
        st.session_state["custom_phase"] = "done"
        st.rerun()

    # ── Phase 5: display results ───────────────────────────────────────────
    if "custom_top" in st.session_state:
        cstats = st.session_state["custom_stats"]
        c_top = st.session_state["custom_top"]
        cpstatus = st.session_state.get("custom_provider_status")

        cm1, cm2, cm3, cm4 = st.columns(4)
        cm1.metric("Tickers Fetched", cstats["fetched"])
        cm2.metric("Passed Gate", cstats["passing"])
        cm3.metric("Ranked", len(c_top))
        cm4.metric("Over-Extended", cstats["over_extended"])

        if cpstatus and cpstatus.warnings:
            with st.expander("Data quality notices", expanded=False):
                for warn in cpstatus.warnings:
                    st.caption(f"⚠ {warn}")

        st.divider()

        if not c_top:
            st.warning(
                "No tickers passed the Forward-Momentum gate. "
                "Possible causes: price below SMA-200, negative 12-1 "
                "month return, or fewer than 3 analyst opinions. "
                "Check logs for details."
            )
        else:
            c_analyst_src = (
                cpstatus.analyst_source.capitalize()
                if cpstatus
                else "Finnhub/yfinance"
            )
            c_passed_pct = (
                cstats["passing"] / cstats["fetched"] * 100
                if cstats["fetched"]
                else 0.0
            )
            st.subheader(f"Custom Analysis — {len(c_top)} Ticker(s) Ranked")
            st.caption(
                f"{cstats['fetched']} fetched · "
                f"{cstats['passing']} passed gate "
                f"({c_passed_pct:.1f}%) · "
                f"{cstats['over_extended']} over-extended (score ×0.90) · "
                f"analyst source: {c_analyst_src}"
            )

            c_rows = [
                {
                    "Rank": s.rank,
                    "Ticker": s.ticker,
                    "Company": s.company,
                    "Score": s.conviction_score,
                    "RS (12-1)": s.relative_strength_score,
                    "EPS Rev.": s.eps_revision_score,
                    "Rating Drift": s.rating_drift_score,
                    "Trend Q.": s.trend_quality_score,
                    "Upside Gap": s.upside_gap_score,
                    "Consensus": s.consensus_strength_score,
                    "Ext. %": s.extension_pct * 100.0,
                    "Stretched": "⚠" if s.over_extended else "",
                    "Rule of 40": s.rule_of_40,
                    "Earn. Quality": s.earnings_quality,
                }
                for s in c_top
            ]
            c_df = pd.DataFrame(c_rows)

            st.dataframe(
                c_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Rank": st.column_config.NumberColumn(
                        "Rank", width="small"
                    ),
                    "Score": st.column_config.NumberColumn(
                        "Score", format="%.1f"
                    ),
                    "RS (12-1)": st.column_config.NumberColumn(
                        "RS (12-1)", format="%.1f"
                    ),
                    "EPS Rev.": st.column_config.NumberColumn(
                        "EPS Rev.", format="%.1f"
                    ),
                    "Rating Drift": st.column_config.NumberColumn(
                        "Rating Drift", format="%.1f"
                    ),
                    "Trend Q.": st.column_config.NumberColumn(
                        "Trend Q.", format="%.1f"
                    ),
                    "Upside Gap": st.column_config.NumberColumn(
                        "Upside Gap", format="%.1f"
                    ),
                    "Consensus": st.column_config.NumberColumn(
                        "Consensus", format="%.1f"
                    ),
                    "Ext. %": st.column_config.NumberColumn(
                        "Ext. %", format="%.2f"
                    ),
                    "Rule of 40": st.column_config.NumberColumn(
                        "Rule of 40", format="%.1f"
                    ),
                    "Earn. Quality": st.column_config.NumberColumn(
                        "Earn. Quality", format="%.2f"
                    ),
                },
            )

        if st.button("Run New Custom Analysis", key="custom_reset_btn"):
            for key in (
                "custom_top",
                "custom_stats",
                "custom_phase",
                "custom_provider_status",
                "custom_tickers",
            ):
                st.session_state.pop(key, None)
            st.rerun()
