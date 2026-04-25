"""yfinance wrapper for per-ticker financial data fetching."""

from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf

from alphavision.models import TickerData

# Alternatives considered:
# - Alpha Vantage / Polygon.io: require API keys with rate limits; yfinance
#   provides equivalent data for free with no registration required.
# - Direct exchange feeds: require FTP agreements and proprietary parsing.
# - pandas_datareader: maintenance mode, deprecated yfinance backend.
# yfinance is the de-facto standard free data source for equity research.

logger = logging.getLogger(__name__)

_TRADING_DAYS_6M: int = 126
_TRADING_DAYS_200: int = 200
_HISTORY_PERIOD: str = "1y"


def _extract_analyst_counts(
    recommendations_summary: object,
) -> tuple[int, int]:
    """Extract strong_buy and buy counts from a recommendations DataFrame.

    Args:
        recommendations_summary: The recommendations_summary attribute from
            a yfinance Ticker object.

    Returns:
        Tuple of (strong_buy_count, buy_count); (0, 0) on any parse failure.
    """
    if not isinstance(recommendations_summary, pd.DataFrame):
        return 0, 0
    if (
        recommendations_summary.empty
        or "period" not in recommendations_summary.columns
    ):
        return 0, 0
    current = recommendations_summary[
        recommendations_summary["period"] == "0m"
    ]
    if current.empty:
        return 0, 0
    try:
        strong_buy = (
            int(current["strongBuy"].iloc[0])
            if "strongBuy" in current.columns
            else 0
        )
        buy = int(current["buy"].iloc[0]) if "buy" in current.columns else 0
    except (TypeError, ValueError):
        return 0, 0
    return strong_buy, buy


def _extract_eps_revision(eps_trend: object) -> float:
    """Estimate EPS revision direction from earnings trend data.

    Compares the current EPS estimate to the 30-days-ago estimate for the
    nearest forecast period. Positive means upward revisions.

    Args:
        eps_trend: The result of yfinance Ticker.get_eps_trend().

    Returns:
        Normalised revision direction; 0.0 if data is unavailable or
        cannot be parsed.
    """
    if not isinstance(eps_trend, pd.DataFrame) or eps_trend.empty:
        return 0.0
    row = eps_trend.iloc[0]
    if "current" not in row.index or "30daysAgo" not in row.index:
        return 0.0
    try:
        current = float(row["current"])
        ago_30 = float(row["30daysAgo"])
    except (TypeError, ValueError):
        return 0.0
    if ago_30 == 0:
        return 0.0
    return (current - ago_30) / abs(ago_30)


def fetch_ticker(ticker: str) -> TickerData:
    """Fetch all required data for one ticker via yfinance.

    Retrieves 1-year price history to compute 6-month price metrics and
    SMA-200, then fetches analyst consensus data from ticker.info and
    recommendations_summary.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL").

    Returns:
        TickerData populated with price history and analyst metrics.

    Raises:
        ValueError: If price history is missing or too short to be useful.
    """
    t = yf.Ticker(ticker)
    hist = t.history(period=_HISTORY_PERIOD)

    if not isinstance(hist, pd.DataFrame) or hist.empty or len(hist) < 2:
        raise ValueError(f"Insufficient price history for ticker '{ticker}'.")

    closes = hist["Close"]
    current_price = float(closes.iloc[-1])

    lookback = min(_TRADING_DAYS_6M, len(closes))
    price_6m_high = float(closes.iloc[-lookback:].max())
    price_6m_start = float(closes.iloc[-lookback])

    drawdown_pct = (
        (current_price - price_6m_high) / price_6m_high
        if price_6m_high > 0
        else 0.0
    )
    return_6m = (
        (current_price - price_6m_start) / price_6m_start
        if price_6m_start > 0
        else 0.0
    )

    sma_window = min(_TRADING_DAYS_200, len(closes))
    sma_200 = float(closes.iloc[-sma_window:].mean())

    info = t.info
    raw_name = info.get("longName") if isinstance(info, dict) else None
    company = str(raw_name) if raw_name is not None else ticker

    raw_target = (
        info.get("targetMeanPrice") if isinstance(info, dict) else None
    )
    target_mean_price: float | None = (
        float(raw_target) if isinstance(raw_target, (int, float)) else None
    )
    raw_count = (
        info.get("numberOfAnalystOpinions") if isinstance(info, dict) else None
    )
    analyst_count = (
        int(raw_count) if isinstance(raw_count, (int, float)) else 0
    )

    strong_buy_count, buy_count = _extract_analyst_counts(
        t.recommendations_summary
    )
    eps_revision_direction = _extract_eps_revision(t.get_eps_trend())

    return TickerData(
        ticker=ticker,
        company=company,
        current_price=current_price,
        price_6m_high=price_6m_high,
        drawdown_pct=drawdown_pct,
        sma_200=sma_200,
        return_6m=return_6m,
        target_mean_price=target_mean_price,
        analyst_count=analyst_count,
        strong_buy_count=strong_buy_count,
        buy_count=buy_count,
        eps_revision_direction=eps_revision_direction,
    )


def fetch_universe(tickers: list[str]) -> list[TickerData]:
    """Fetch data for all tickers, skipping any that fail.

    Args:
        tickers: List of stock ticker symbols.

    Returns:
        List of TickerData; tickers that raise an exception are omitted.
    """
    results: list[TickerData] = []
    for ticker in tickers:
        try:
            results.append(fetch_ticker(ticker))
        except Exception as exc:
            logger.warning("Skipping ticker '%s': %s", ticker, exc)
    return results
