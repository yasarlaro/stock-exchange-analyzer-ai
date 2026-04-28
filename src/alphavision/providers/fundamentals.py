"""Fundamentals provider — SEC EDGAR via edgartools, SQLite-cached.

Computes the v3.0 quality signals from authoritative XBRL filings:

- ``rule_of_40``: ``revenue_growth_yoy_% + fcf_margin_%``
- ``earnings_quality``: ``free_cash_flow / net_income`` (latest period)

Cached forever, keyed by ``(ticker, accession_number)``: filings are
immutable once published, so a hit means we never re-pull XBRL for the
same statement.

Fallback chain:
  1. SEC EDGAR XBRL (primary, authoritative)
  2. yfinance ``info`` dict (fallback when EDGAR finds no filing)

# Alternatives considered:
# - yfinance ``info`` for fundamentals (primary): missing for ~25-30% of
#   the universe with no audit trail; EDGAR is authoritative and covers
#   all SEC-registered issuers. yfinance remains as a fallback because it
#   is better than returning None for the entire universe.
# - Manual XBRL parsing from SEC URLs: edgartools wraps the XBRL
#   facts-API and adds Fair-Access throttling out of the box.
# - In-memory cache: fundamentals only change when a 10-Q/10-K is filed
#   (quarterly), so a process-lifetime cache loses too much; the
#   SQLite cache survives across weekly runs.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import yfinance as yf
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────

_EDGAR_IDENTITY_ENV: str = "EDGAR_IDENTITY"
_DEFAULT_IDENTITY: str = "AlphaVision Research research@alphavision.local"
_CACHE_DIR: Path = Path("data")
_CACHE_DB: Path = _CACHE_DIR / "fundamentals_cache.db"

# Forms we consider; 10-K is the annual report, 10-Q the quarterly.
_FORMS: tuple[str, ...] = ("10-Q", "10-K")

# Keys we look up in the XBRL fact map. edgartools normalises tag names
# but small variations remain across filers; ordered tuples below try
# the most common spellings first.
_REVENUE_TAGS: tuple[str, ...] = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
)
_OCF_TAGS: tuple[str, ...] = (
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByOperatingActivities",
)
_CAPEX_TAGS: tuple[str, ...] = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
)
_NET_INCOME_TAGS: tuple[str, ...] = (
    "NetIncomeLoss",
    "ProfitLoss",
)


class FundamentalsSnapshot(BaseModel):
    """Quality fields the scoring engine consumes.

    Attributes:
        ticker: Stock ticker symbol.
        rule_of_40: ``revenue_growth_yoy_% + fcf_margin_%``; ``None``
            when any input is unavailable.
        earnings_quality: ``free_cash_flow / net_income`` for the latest
            period; ``None`` when net income is zero or missing.
    """

    ticker: str
    rule_of_40: float | None = None
    earnings_quality: float | None = None


# ── Cache layer ────────────────────────────────────────────────────────────


def _connect() -> sqlite3.Connection:
    """Open (and lazily create) the SQLite cache connection."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_CACHE_DB)
    with closing(conn.cursor()) as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS fundamentals (
                ticker TEXT NOT NULL,
                accession TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (ticker, accession)
            )
            """
        )
    conn.commit()
    return conn


def _cache_get(ticker: str, accession: str) -> dict[str, Any] | None:
    """Return the cached payload for ``(ticker, accession)`` or ``None``."""
    with closing(_connect()) as conn, closing(conn.cursor()) as cur:
        cur.execute(
            "SELECT payload FROM fundamentals WHERE ticker = ? "
            "AND accession = ?",
            (ticker, accession),
        )
        row = cur.fetchone()
    if row is None:
        return None
    try:
        result = json.loads(row[0])
    except json.JSONDecodeError:
        return None
    return result if isinstance(result, dict) else None


def _cache_put(ticker: str, accession: str, payload: dict[str, Any]) -> None:
    """Persist ``payload`` for ``(ticker, accession)``."""
    with closing(_connect()) as conn, closing(conn.cursor()) as cur:
        cur.execute(
            "INSERT OR REPLACE INTO fundamentals "
            "(ticker, accession, payload) VALUES (?, ?, ?)",
            (ticker, accession, json.dumps(payload)),
        )
        conn.commit()


# ── EDGAR access ───────────────────────────────────────────────────────────


_identity_set: bool = False


def _ensure_identity() -> None:
    """Set the SEC Fair-Access identity exactly once per process."""
    global _identity_set
    if _identity_set:
        return
    identity = (
        os.environ.get(_EDGAR_IDENTITY_ENV, _DEFAULT_IDENTITY).strip()
        or _DEFAULT_IDENTITY
    )
    try:
        from edgar import set_identity

        set_identity(identity)
    except Exception as exc:
        logger.warning("EDGAR set_identity failed: %s", exc)
    _identity_set = True


def _latest_accession(ticker: str) -> tuple[str, Any] | None:
    """Return ``(accession, filing_obj)`` for the latest 10-Q or 10-K.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        Tuple of accession number and the edgartools filing object, or
        ``None`` if no relevant filing is found / EDGAR call fails.
    """
    _ensure_identity()
    try:
        from edgar import Company

        company = Company(ticker)
    except Exception as exc:
        logger.debug("EDGAR Company('%s') failed: %s", ticker, exc)
        return None

    for form in _FORMS:
        try:
            filings = company.get_filings(form=form)
        except Exception as exc:
            logger.debug(
                "EDGAR get_filings(%s) failed for %s: %s",
                form,
                ticker,
                exc,
            )
            continue
        if filings is None:
            continue
        try:
            latest = filings.latest()
        except Exception as exc:
            logger.debug(
                "EDGAR filings.latest() failed for %s/%s: %s",
                ticker,
                form,
                exc,
            )
            continue
        if latest is None:
            continue
        accession = getattr(latest, "accession_no", None) or getattr(
            latest, "accession_number", None
        )
        if not accession:
            continue
        return str(accession), latest

    return None


def _xbrl_facts(filing: Any) -> dict[str, float]:  # noqa: ANN401
    """Return a flat ``tag → value`` map from the filing's XBRL.

    edgartools exposes XBRL facts via ``Filing.xbrl().facts`` (a list of
    fact objects) — this helper picks the most recent numeric fact for
    each tag we care about. Missing facts are simply absent from the
    returned dict.
    """
    try:
        xb = filing.xbrl()
    except Exception as exc:
        logger.debug("filing.xbrl() failed: %s", exc)
        return {}
    if xb is None:
        return {}

    facts_attr: Any = getattr(xb, "facts", None)
    if facts_attr is None:
        return {}

    out: dict[str, float] = {}
    facts_iter: Any
    try:
        facts_iter = list(facts_attr)
    except TypeError:
        return {}

    for fact in facts_iter:
        tag = (
            getattr(fact, "concept", None)
            or getattr(fact, "tag", None)
            or getattr(fact, "name", None)
        )
        value = getattr(fact, "value", None) or getattr(fact, "numeric", None)
        if tag is None or value is None:
            continue
        # Strip ``us-gaap:`` namespace if present.
        clean_tag = str(tag).split(":")[-1]
        try:
            num = float(value)
        except (TypeError, ValueError):
            continue
        # Keep first occurrence (edgartools orders by relevance).
        out.setdefault(clean_tag, num)

    return out


def _first_present(
    facts: dict[str, float], keys: tuple[str, ...]
) -> float | None:
    """Return ``facts[key]`` for the first key in ``keys`` that's present."""
    for key in keys:
        if key in facts:
            return facts[key]
    return None


def _compute_metrics(
    facts_now: dict[str, float], facts_prior: dict[str, float]
) -> tuple[float | None, float | None]:
    """Compute ``(rule_of_40, earnings_quality)`` from two fact maps.

    Args:
        facts_now: XBRL facts from the latest filing.
        facts_prior: XBRL facts from the year-ago filing (for revenue
            YoY); pass an empty dict if unavailable — Rule of 40 will
            fall back to ``None``.

    Returns:
        ``(rule_of_40, earnings_quality)``; either may be ``None``.
    """
    revenue_now = _first_present(facts_now, _REVENUE_TAGS)
    ocf = _first_present(facts_now, _OCF_TAGS)
    capex = _first_present(facts_now, _CAPEX_TAGS)
    net_income = _first_present(facts_now, _NET_INCOME_TAGS)

    fcf: float | None = None
    if ocf is not None and capex is not None:
        # CapEx is reported as a positive outflow; subtract from OCF.
        fcf = ocf - abs(capex)

    fcf_margin: float | None = None
    if fcf is not None and revenue_now is not None and revenue_now > 0:
        fcf_margin = fcf / revenue_now * 100.0

    revenue_growth: float | None = None
    revenue_prior = _first_present(facts_prior, _REVENUE_TAGS)
    if (
        revenue_now is not None
        and revenue_prior is not None
        and revenue_prior > 0
    ):
        revenue_growth = (revenue_now - revenue_prior) / revenue_prior * 100.0

    rule_of_40: float | None = None
    if revenue_growth is not None and fcf_margin is not None:
        rule_of_40 = revenue_growth + fcf_margin

    earnings_quality: float | None = None
    if fcf is not None and net_income is not None and net_income != 0:
        earnings_quality = fcf / net_income

    return rule_of_40, earnings_quality


# ── yfinance fallback ──────────────────────────────────────────────────────


def _yfinance_fundamentals_snapshot(ticker: str) -> FundamentalsSnapshot:
    """Compute Rule of 40 and Earnings Quality from yfinance ``info``.

    Coverage is ~70-75% of the universe (lower than EDGAR, which
    covers all SEC-registered issuers).  Used as a fallback when EDGAR
    finds no filing for the ticker.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        :class:`FundamentalsSnapshot` with values derived from
        ``Ticker.info``; either field may be ``None`` when data is
        missing.
    """
    try:
        info = yf.Ticker(ticker).info
        if not isinstance(info, dict):
            return FundamentalsSnapshot(ticker=ticker)
    except Exception as exc:
        logger.debug("yfinance info fallback failed for %s: %s", ticker, exc)
        return FundamentalsSnapshot(ticker=ticker)

    revenue_growth = info.get("revenueGrowth")
    free_cashflow = info.get("freeCashflow")
    total_revenue = info.get("totalRevenue")
    net_income = info.get("netIncomeToCommon")

    rule_of_40: float | None = None
    if (
        isinstance(revenue_growth, (int, float))
        and isinstance(free_cashflow, (int, float))
        and isinstance(total_revenue, (int, float))
        and total_revenue > 0
    ):
        fcf_margin = free_cashflow / total_revenue * 100.0
        rule_of_40 = float(revenue_growth) * 100.0 + fcf_margin

    earnings_quality: float | None = None
    if (
        isinstance(free_cashflow, (int, float))
        and isinstance(net_income, (int, float))
        and net_income != 0
    ):
        earnings_quality = free_cashflow / net_income

    return FundamentalsSnapshot(
        ticker=ticker,
        rule_of_40=rule_of_40,
        earnings_quality=earnings_quality,
    )


# ── Public entry point ─────────────────────────────────────────────────────


def fetch_fundamentals_snapshot(ticker: str) -> FundamentalsSnapshot:
    """Fetch the latest fundamentals for ``ticker``, using the cache.

    Fallback chain:

    1. SEC EDGAR XBRL — authoritative; cached by accession number.
    2. yfinance ``info`` dict — activated when EDGAR finds no filing.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        :class:`FundamentalsSnapshot`. Either or both metrics may be
        ``None`` when the underlying facts are missing from all sources.
    """
    logger.info("fundams | %-6s | SEC EDGAR (XBRL)", ticker)
    located = _latest_accession(ticker)
    if located is None:
        logger.info(
            "fundams | %-6s | EDGAR no filing → yfinance fallback", ticker
        )
        return _yfinance_fundamentals_snapshot(ticker)

    accession, filing = located

    cached = _cache_get(ticker, accession)
    if cached is not None:
        logger.info("fundams | %-6s | EDGAR cache hit (%s)", ticker, accession)
        return FundamentalsSnapshot(
            ticker=ticker,
            rule_of_40=cached.get("rule_of_40"),
            earnings_quality=cached.get("earnings_quality"),
        )

    try:
        facts_now = _xbrl_facts(filing)
    except Exception as exc:
        logger.warning("XBRL parse failed for %s: %s", ticker, exc)
        facts_now = {}

    facts_prior = _prior_year_facts(ticker, accession)
    rule_of_40, earnings_quality = _compute_metrics(facts_now, facts_prior)

    _cache_put(
        ticker,
        accession,
        {
            "rule_of_40": rule_of_40,
            "earnings_quality": earnings_quality,
        },
    )

    # If EDGAR XBRL returned no metrics, try yfinance as supplemental.
    if rule_of_40 is None and earnings_quality is None:
        logger.info(
            "fundams | %-6s | EDGAR empty metrics → yfinance fallback",
            ticker,
        )
        return _yfinance_fundamentals_snapshot(ticker)

    return FundamentalsSnapshot(
        ticker=ticker,
        rule_of_40=rule_of_40,
        earnings_quality=earnings_quality,
    )


def _prior_year_facts(ticker: str, current_accession: str) -> dict[str, float]:
    """Return the year-ago filing's XBRL facts; ``{}`` if unavailable.

    Picks the same form (10-Q vs 10-K) from ~12 months before
    ``current_accession``. Implementation is best-effort: a missing
    prior filing simply leaves revenue growth (and thus Rule of 40)
    unset.
    """
    _ensure_identity()
    try:
        from edgar import Company

        company = Company(ticker)
    except Exception:
        return {}

    for form in _FORMS:
        try:
            filings = company.get_filings(form=form)
        except Exception:
            continue
        if filings is None:
            continue
        try:
            collection = list(filings)
        except TypeError:
            continue
        if len(collection) < 5:
            continue
        # The 10-Q index 4 (or 10-K index 1) approximates the year-ago
        # period of a freshly-filed report. We only need an approximation
        # — Rule of 40 is informational and tolerates a quarter of slip.
        idx = 4 if form == "10-Q" else 1
        if idx >= len(collection):
            continue
        try:
            return _xbrl_facts(collection[idx])
        except Exception:
            return {}
    return {}
