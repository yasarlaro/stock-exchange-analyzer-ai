"""S&P 500 and Nasdaq-100 equity universe builder."""

from __future__ import annotations

import io
import logging
import time

import pandas as pd
import requests

# Alternatives considered:
# - Direct Wikipedia page scraping: blocked by 403 rate-limit on rapid fetches
# - Alpha Vantage API: requires API key + rate limits (500 req/day free)
# - pandas_datareader: unstable Wikipedia endpoint, maintenance mode
# - Exchange CSV feeds: require registration and aren't consistently formatted
# Wikipedia Action API (w/api.php): official programmatic interface, no key
# required, 500 req/10s rate limit — correct tool for constituent tables.
_WIKI_API = "https://en.wikipedia.org/w/api.php"
_SP500_PAGE = "List of S&P 500 companies"
_NDX100_PAGE = "Nasdaq-100"

_HEADERS = {
    "User-Agent": (
        "AlphaVision/1.0 (educational equity research; "
        "github.com/yasarlaro/stock-exchange-analyzer-ai)"
    )
}

logger = logging.getLogger(__name__)


def _fetch_wikipedia_html(page: str) -> str:
    """Fetch Wikipedia page content via the official Action API.

    Args:
        page: Wikipedia page title (e.g. "Nasdaq-100").

    Returns:
        Rendered HTML of the page content as a string.

    Raises:
        RuntimeError: If the Wikipedia API returns an error payload.
        requests.HTTPError: If the HTTP request fails.
    """
    params = {
        "action": "parse",
        "page": page,
        "prop": "text",
        "format": "json",
        "redirects": "1",
    }
    resp = requests.get(_WIKI_API, params=params, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(
            f"Wikipedia API error for '{page}': {data['error']}"
        )
    return str(data["parse"]["text"]["*"])


def get_sp500() -> pd.DataFrame:
    """Fetch current S&P 500 constituents from Wikipedia.

    Returns:
        DataFrame with columns: ticker, company, sector.

    Raises:
        RuntimeError: If the Wikipedia page cannot be fetched or parsed.
    """
    try:
        html = _fetch_wikipedia_html(_SP500_PAGE)
        tables = pd.read_html(io.StringIO(html), attrs={"id": "constituents"})
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch S&P 500 constituent table: {exc}"
        ) from exc

    if not tables:
        raise RuntimeError("No tables found on S&P 500 Wikipedia page.")

    df = tables[0]
    df = df.rename(
        columns={
            "Symbol": "ticker",
            "Security": "company",
            "GICS Sector": "sector",
        }
    )
    df["ticker"] = df["ticker"].str.replace(".", "-", regex=False)
    result = df[["ticker", "company", "sector"]].copy()
    logger.info("Fetched %d S&P 500 tickers.", len(result))
    return result


def get_nasdaq100() -> pd.DataFrame:
    """Fetch current Nasdaq-100 constituents from Wikipedia.

    Returns:
        DataFrame with columns: ticker, company, sector.

    Raises:
        RuntimeError: If the Wikipedia page cannot be fetched or parsed.
    """
    try:
        html = _fetch_wikipedia_html(_NDX100_PAGE)
        tables = pd.read_html(io.StringIO(html), attrs={"id": "constituents"})
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch Nasdaq-100 constituent table: {exc}"
        ) from exc

    if not tables:
        raise RuntimeError("No tables found on Nasdaq-100 Wikipedia page.")

    df = tables[0]

    # Alternatives considered:
    # - Hard-coding column positions (fragile if Wikipedia edits the table)
    # - Using the first table on the page (wrong table selected historically)
    # The constituents table id is stable; rename only the columns we need.
    # Note: "subsector" contains "sector" — use a mapped set to take only
    # the first match per target and exclude sub-* columns from sector.
    rename_map: dict[str, str] = {}
    mapped: set[str] = set()
    for col in df.columns:
        col_lower = col.lower()
        if "ticker" not in mapped and (
            "ticker" in col_lower or "symbol" in col_lower
        ):
            rename_map[col] = "ticker"
            mapped.add("ticker")
        elif "company" not in mapped and (
            "company" in col_lower or "security" in col_lower
        ):
            rename_map[col] = "company"
            mapped.add("company")
        elif (
            "sector" not in mapped
            and "sub" not in col_lower
            and ("sector" in col_lower or "industry" in col_lower)
        ):
            rename_map[col] = "sector"
            mapped.add("sector")

    df = df.rename(columns=rename_map)

    for col in ("ticker", "company", "sector"):
        if col not in df.columns:
            df[col] = ""

    df["ticker"] = df["ticker"].str.replace(".", "-", regex=False)
    result = df[["ticker", "company", "sector"]].copy()
    logger.info("Fetched %d Nasdaq-100 tickers.", len(result))
    return result


def build_universe() -> pd.DataFrame:
    """Build the full equity universe from S&P 500 and Nasdaq-100.

    Deduplicates tickers that appear in both indices and adds a
    'source' column indicating membership: 'SP500', 'NDX100', or 'BOTH'.

    Returns:
        DataFrame with columns: ticker, company, sector, source.
        Sorted alphabetically by ticker.

    Raises:
        RuntimeError: If either constituent list cannot be fetched.
    """
    sp500 = get_sp500().assign(source="SP500")
    time.sleep(1)  # Courtesy pause between consecutive API calls
    ndx100 = get_nasdaq100().assign(source="NDX100")

    sp500_tickers = set(sp500["ticker"])
    ndx100_tickers = set(ndx100["ticker"])
    both = sp500_tickers & ndx100_tickers

    combined = pd.concat([sp500, ndx100], ignore_index=True)
    combined = combined.drop_duplicates(subset="ticker", keep="first")

    combined.loc[combined["ticker"].isin(both), "source"] = "BOTH"
    combined = combined.sort_values("ticker").reset_index(drop=True)

    logger.info(
        "Universe built: %d tickers (%d SP500-only, %d NDX100-only, %d BOTH).",
        len(combined),
        len(sp500_tickers - ndx100_tickers),
        len(ndx100_tickers - sp500_tickers),
        len(both),
    )
    return combined
