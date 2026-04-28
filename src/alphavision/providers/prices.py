"""Price-history provider — yfinance ``history()`` only.

Returns a :class:`PriceSnapshot` with current price, 20- and 200-day SMAs,
the Jegadeesh-Titman 12-1 month return, and the company's long name.

# Alternatives considered:
# - Polygon.io / Alpha Vantage: free tiers are too rate-limited for a
#   ~520-ticker weekly run; both require API keys.
# - Stooq CSV mirror: useful as a defensive fallback, but yfinance has
#   been the reliable part of the stack — the failure mode in v2.0 was
#   in `Ticker.info` (analyst data), not `Ticker.history()`.
# - Direct exchange feeds: require FTP agreements and parsing.
"""

from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_HISTORY_PERIOD: str = "1y"
_TRADING_DAYS_12M: int = 252
_TRADING_DAYS_1M: int = 21
_TRADING_DAYS_200: int = 200
_TRADING_DAYS_20: int = 20


class PriceSnapshot(BaseModel):
    """Subset of :class:`alphavision.models.TickerData` that this
    provider is responsible for.

    Attributes:
        ticker: Stock ticker symbol.
        company: Company long name; falls back to ticker on missing data.
        current_price: Most recent closing price.
        sma_20: 20-day simple moving average.
        sma_200: 200-day simple moving average.
        return_12_1: Jegadeesh-Titman 12-1 month return.
    """

    ticker: str
    company: str
    current_price: float
    sma_20: float
    sma_200: float
    return_12_1: float


def compute_return_12_1(closes: pd.Series) -> float:
    """Compute the Jegadeesh-Titman 12-1 month return.

    The 12-1 window measures the return from ~12 months ago to ~1 month
    ago, deliberately excluding the most recent month to sidestep
    short-term reversal noise. Falls back to the earliest available
    history if the series is shorter than 12 months.

    Args:
        closes: Pandas Series of closing prices, oldest first.

    Returns:
        12-1 return as a decimal (e.g. ``0.18`` for +18%); ``0.0`` if
        the window cannot be evaluated.
    """
    n = len(closes)
    if n < 2:
        return 0.0
    lookback_12 = min(_TRADING_DAYS_12M, n)
    lookback_1 = min(_TRADING_DAYS_1M, max(1, lookback_12 - 1))
    price_12m_ago = float(closes.iloc[-lookback_12])
    price_1m_ago = float(closes.iloc[-lookback_1])
    if price_12m_ago <= 0:
        return 0.0
    return price_1m_ago / price_12m_ago - 1.0


def _company_name(info: object, ticker: str) -> str:
    """Return ``info["longName"]`` if present and non-empty, else ticker."""
    if isinstance(info, dict):
        raw = info.get("longName")
        if isinstance(raw, str) and raw:
            return raw
    return ticker


def fetch_price_snapshot(ticker: str) -> PriceSnapshot:
    """Fetch 1-year price history for ``ticker`` and derive the snapshot.

    Args:
        ticker: Stock ticker symbol (e.g. ``"AAPL"``).

    Returns:
        Populated :class:`PriceSnapshot`.

    Raises:
        ValueError: If price history is empty or shorter than two rows.
    """
    logger.info("prices  | %-6s | yfinance history()", ticker)
    t = yf.Ticker(ticker)
    hist = t.history(period=_HISTORY_PERIOD)
    if not isinstance(hist, pd.DataFrame) or hist.empty or len(hist) < 2:
        raise ValueError(f"Insufficient price history for ticker '{ticker}'.")

    closes = hist["Close"]
    current_price = float(closes.iloc[-1])

    sma_20_window = min(_TRADING_DAYS_20, len(closes))
    sma_20 = float(closes.iloc[-sma_20_window:].mean())

    sma_200_window = min(_TRADING_DAYS_200, len(closes))
    sma_200 = float(closes.iloc[-sma_200_window:].mean())

    return_12_1 = compute_return_12_1(closes)

    company = _company_name(_safe_info(t), ticker)

    return PriceSnapshot(
        ticker=ticker,
        company=company,
        current_price=current_price,
        sma_20=sma_20,
        sma_200=sma_200,
        return_12_1=return_12_1,
    )


def _extract_closes_from_batch(
    data: pd.DataFrame,
    ticker: str,
    is_multi: bool,
) -> pd.Series:
    """Return the Close series for ``ticker`` from a ``yf.download()`` result.

    Handles both flat-column (single-ticker) and MultiIndex (multi-ticker)
    DataFrame layouts produced by different yfinance versions.

    Args:
        data: DataFrame returned by ``yf.download()``.
        ticker: Ticker to extract.
        is_multi: ``True`` when ``data.columns`` is a MultiIndex.

    Returns:
        Cleaned Close series with NaN rows dropped; empty on any error.
    """
    if not is_multi:
        col = data.get("Close")
        if col is None:
            return pd.Series(dtype=float)
        return col.dropna()
    try:
        series: pd.Series[float] = data[ticker]["Close"].dropna()
        return series
    except KeyError:
        return pd.Series(dtype=float)


def fetch_price_batch(
    tickers: list[str],
    company_lookup: dict[str, str] | None = None,
) -> dict[str, PriceSnapshot]:
    """Batch-fetch 1-year price history for all tickers via ``yf.download()``.

    Collapses ~511 individual ``history()`` calls into a single batched
    download session, reducing Phase 1 wall-clock time from ~85 s (3
    workers × ~0.5 s each) to under 30 s for the full S&P 500 + NDX
    universe.  Tickers with fewer than two data points are silently omitted.

    # Alternatives considered:
    # - Individual fetch_price_snapshot calls in parallel: already in use
    #   via fetch_universe; the bottleneck is HTTP round-trips, not CPU.
    #   yf.download() reuses the same session for all tickers.
    # - Stooq / Alpha Vantage batch: require API keys or have lower rate
    #   limits; yfinance download is key-free and handles 511 tickers well.

    Args:
        tickers: Stock ticker symbols to fetch.
        company_lookup: Optional ``{ticker: company_name}`` mapping. When
            absent, ticker symbol is used as the company name.

    Returns:
        Dict mapping ticker → :class:`PriceSnapshot`; tickers with
        insufficient history are omitted from the result.
    """
    if not tickers:
        return {}

    logger.info("prices  | batch  | yf.download() %d tickers", len(tickers))
    lookup = company_lookup or {}

    try:
        raw = yf.download(
            tickers=tickers,
            period=_HISTORY_PERIOD,
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as exc:
        logger.warning("yf.download() failed: %s", exc)
        return {}

    if not isinstance(raw, pd.DataFrame) or raw.empty:
        logger.warning("yf.download() returned empty DataFrame.")
        return {}

    is_multi = isinstance(raw.columns, pd.MultiIndex)
    result: dict[str, PriceSnapshot] = {}

    for ticker in tickers:
        try:
            closes = _extract_closes_from_batch(raw, ticker, is_multi)
            if closes.empty or len(closes) < 2:
                logger.debug(
                    "Insufficient batch history for %s — skipping.", ticker
                )
                continue

            current_price = float(closes.iloc[-1])
            sma_20_w = min(_TRADING_DAYS_20, len(closes))
            sma_200_w = min(_TRADING_DAYS_200, len(closes))
            sma_20 = float(closes.iloc[-sma_20_w:].mean())
            sma_200 = float(closes.iloc[-sma_200_w:].mean())
            ret_12_1 = compute_return_12_1(closes)

            result[ticker] = PriceSnapshot(
                ticker=ticker,
                company=lookup.get(ticker, ticker),
                current_price=current_price,
                sma_20=sma_20,
                sma_200=sma_200,
                return_12_1=ret_12_1,
            )
        except Exception as exc:
            logger.warning(
                "Batch price extraction failed for %s: %s", ticker, exc
            )

    logger.info(
        "prices  | batch  | %d of %d snapshots extracted",
        len(result),
        len(tickers),
    )
    return result


def _safe_info(t: yf.Ticker) -> object:
    """Return ``t.info`` or ``None`` if the call raises (e.g. ETF 404)."""
    try:
        return t.info
    except Exception as exc:
        logger.debug("yfinance .info failed: %s", exc)
        return None


def fetch_benchmark_return_12_1(ticker: str = "SPY") -> float:
    """Fetch ``ticker``'s 12-1 month return; ``0.0`` on failure.

    Bypasses ``Ticker.info`` (which 404s for ETFs in yfinance) by going
    straight to ``history()``.

    Args:
        ticker: Benchmark ticker (default ``"SPY"``).

    Returns:
        12-1 return for the benchmark, or ``0.0`` on any error.
    """
    try:
        bench = yf.Ticker(ticker)
        hist = bench.history(period=_HISTORY_PERIOD)
        if not isinstance(hist, pd.DataFrame) or hist.empty or len(hist) < 2:
            logger.warning("Benchmark history unavailable for %s.", ticker)
            return 0.0
        return compute_return_12_1(hist["Close"])
    except Exception as exc:
        logger.warning("Benchmark fetch failed for %s: %s", ticker, exc)
        return 0.0


def is_rate_limited(exc: Exception) -> bool:
    """True if ``exc`` looks like a Yahoo Finance rate-limit response."""
    msg = str(exc)
    return "Too Many Requests" in msg or "Rate limited" in msg
