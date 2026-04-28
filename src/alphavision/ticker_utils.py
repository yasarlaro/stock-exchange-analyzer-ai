"""Ticker input parsing and universe validation utilities."""

from __future__ import annotations

import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)

# Alternatives considered:
# - Splitting only on commas: users naturally type "AAPL MSFT" with spaces;
#   a whitespace-aware split avoids a hard UX failure.
# - Regex validation against a known exchange symbol pattern: adds complexity
#   with diminishing value — invalid symbols are caught at fetch time with a
#   clear ValueError from the price provider.
# - Accepting lowercase input without normalising: yfinance accepts lowercase
#   but Finnhub and EDGAR expect uppercase; always normalise at the boundary.

_TICKER_RE: re.Pattern[str] = re.compile(r"[A-Za-z0-9.\-]+")
_MAX_TICKERS: int = 50


def parse_ticker_input(text: str) -> list[str]:
    """Parse a freeform string of ticker symbols into a deduplicated list.

    Accepts any combination of comma, space, semicolon, or newline as
    delimiters. Symbols are normalised to uppercase.  Non-alphanumeric
    tokens (e.g. empty strings after splitting) are silently discarded.
    Preserves first-occurrence order after deduplication.

    Args:
        text: Raw user input, e.g. ``"AAPL, msft NVDA;GOOGL"``

    Returns:
        Deduplicated, uppercase list of recognised symbol tokens.
        At most ``_MAX_TICKERS`` entries are returned; excess tokens are
        dropped with a warning.

    Examples:
        >>> parse_ticker_input("AAPL, msft  NVDA")
        ['AAPL', 'MSFT', 'NVDA']
        >>> parse_ticker_input("")
        []
    """
    if not text or not text.strip():
        return []

    tokens = _TICKER_RE.findall(text.upper())
    seen: set[str] = set()
    result: list[str] = []
    for tok in tokens:
        if tok and tok not in seen:
            seen.add(tok)
            result.append(tok)

    if len(result) > _MAX_TICKERS:
        logger.warning(
            "parse_ticker_input: %d tokens found; truncating to %d.",
            len(result),
            _MAX_TICKERS,
        )
        result = result[:_MAX_TICKERS]

    return result


def validate_against_universe(
    tickers: list[str],
    universe_df: pd.DataFrame,
) -> tuple[list[str], list[str]]:
    """Split ``tickers`` into those present in the universe and those not.

    The comparison is case-insensitive to guard against display-case
    differences in the universe DataFrame.

    Args:
        tickers: Normalised ticker symbols to validate.
        universe_df: DataFrame with a ``"ticker"`` column, as returned by
            :func:`alphavision.universe.build_universe`.

    Returns:
        ``(in_universe, out_of_universe)`` — both are sub-lists of
        ``tickers`` that preserve input order.
    """
    universe_set: set[str] = set(
        universe_df["ticker"].astype(str).str.upper().tolist()
        if "ticker" in universe_df.columns
        else []
    )
    in_uni: list[str] = []
    out_uni: list[str] = []
    for t in tickers:
        if t.upper() in universe_set:
            in_uni.append(t)
        else:
            out_uni.append(t)
    return in_uni, out_uni
