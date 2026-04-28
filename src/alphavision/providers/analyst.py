"""Analyst provider — Finnhub for ratings/targets, yfinance for EPS slope.

Returns an :class:`AnalystSnapshot` with the analyst-driven inputs to
the v3.0 Conviction Score: net upgrades over the last 30 days, the
multi-period EPS revision slope, the consensus mean target price, the
total analyst count, and the current Strong Buy / Buy ratios.

# Alternatives considered:
# - Finnhub for EPS revisions: the free-tier ``/stock/earnings-estimate``
#   only exposes the *current* consensus, not the historical revision
#   series. yfinance's ``get_eps_trend()`` returns five timestamped
#   snapshots (current, 7d, 30d, 60d, 90d) per quarter — the only free
#   source we have for a slope.
# - FMP / Tiingo: better history coverage but free tiers cap at 250
#   calls/day; insufficient for a ~520-ticker weekly run.
# - OpenBB SDK: meta-wrapper that still requires the upstream API key;
#   adds an abstraction layer without independent data lift.
# - 3-call Finnhub path (/upgrade-downgrade + /recommendation +
#   /price-target): the original design. /upgrade-downgrade was replaced
#   by a month-over-month delta derived from /recommendation (already
#   fetched), cutting Finnhub calls from 3 to 2 per ticker — saving
#   ~8.5 minutes on a 511-ticker universe at the free-tier 60-call/min
#   rate. See ``_recommendation_with_drift`` for the derivation.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import threading
import time
from typing import Any

import pandas as pd
import requests
import yfinance as yf
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Finnhub configuration ──────────────────────────────────────────────────

_FINNHUB_BASE: str = "https://finnhub.io/api/v1"
_FINNHUB_TIMEOUT: float = 10.0
_FINNHUB_API_KEY_ENV: str = "FINNHUB_API_KEY"

# Free-tier rate limit is 60 calls/minute. Pace ourselves so a long
# universe sweep does not trip the limit and force a backoff round.
_FINNHUB_MIN_INTERVAL: float = 1.05  # seconds between calls

# 429 retry strategy.
_FINNHUB_MAX_RETRIES: int = 3
_FINNHUB_BACKOFF_BASE: float = 2.0  # seconds; doubled each retry

# Net-upgrades window — rating changes more than this many days old are
# excluded from the rating-drift signal.
_RATING_DRIFT_WINDOW_DAYS: int = 30


class AnalystSnapshot(BaseModel):
    """Analyst-driven fields the scoring engine consumes.

    Attributes:
        ticker: Stock ticker symbol.
        net_upgrades_30d: Month-over-month change in bullish analyst count
            (strong_buy + buy), derived from ``/stock/recommendation``
            snapshots. Positive = more analysts turned bullish this month.
        eps_revision_slope: Mean fractional revision of the
            forward-quarter EPS estimate vs. its 7d / 30d / 60d / 90d
            historical snapshots; positive = upward revisions.
        target_mean_price: Consensus mean price target; ``None`` when
            the provider returns no value.
        analyst_count: Total analysts contributing to the most recent
            recommendation snapshot.
        strong_buy_count: Strong Buy votes in the most recent snapshot.
        buy_count: Buy votes in the most recent snapshot.
    """

    ticker: str
    net_upgrades_30d: int = 0
    eps_revision_slope: float = 0.0
    target_mean_price: float | None = None
    analyst_count: int = 0
    strong_buy_count: int = 0
    buy_count: int = 0


# ── HTTP layer ─────────────────────────────────────────────────────────────

# ThreadPoolExecutor runs Finnhub calls from multiple threads. Without a
# lock, all threads can read the same _last_call_at, decide no sleep is
# needed, and fire simultaneous requests — Finnhub returns 403 for the
# concurrent burst. The lock serialises entry into _throttle() so only one
# thread advances _last_call_at at a time, guaranteeing the full
# _FINNHUB_MIN_INTERVAL between outgoing calls across all workers.
_last_call_at: float = 0.0
_throttle_lock: threading.Lock = threading.Lock()

# HTTP status codes that are treated as transient rate-limit responses.
# Finnhub returns 429 for explicit rate limits; 403 can appear when
# concurrent burst requests hit the per-second limit simultaneously.
_RETRIABLE_STATUS: frozenset[int] = frozenset({403, 429})


def _throttle() -> None:
    """Serialise Finnhub calls so no two threads fire within the interval.

    Acquires a process-wide lock before measuring and updating
    ``_last_call_at``.  The lock is held while sleeping, which blocks
    other threads from entering until the interval has elapsed — ensuring
    a minimum of ``_FINNHUB_MIN_INTERVAL`` seconds between outgoing calls
    even under parallel fetch workers.
    """
    global _last_call_at
    with _throttle_lock:
        now = time.monotonic()
        delta = now - _last_call_at
        if delta < _FINNHUB_MIN_INTERVAL:
            time.sleep(_FINNHUB_MIN_INTERVAL - delta)
        _last_call_at = time.monotonic()


def _api_key() -> str | None:
    """Read the Finnhub key from the environment; ``None`` if absent."""
    key = os.environ.get(_FINNHUB_API_KEY_ENV, "").strip()
    return key or None


def _finnhub_get(path: str, params: dict[str, str]) -> Any:  # noqa: ANN401
    """Make a rate-limited GET to Finnhub with 429/403-aware retry.

    Both 429 (explicit rate limit) and 403 (burst rejection) are treated
    as transient and retried with exponential backoff.  Other non-200
    responses give up immediately.

    Args:
        path: Path under ``/api/v1`` (e.g. ``"/stock/recommendation"``).
        params: Query-string parameters; the API key is injected.

    Returns:
        Decoded JSON body on 200; ``None`` if the key is missing, the
        request keeps hitting rate-limit errors, or a transport error
        fires after retries are exhausted.
    """
    key = _api_key()
    if key is None:
        logger.debug("FINNHUB_API_KEY unset; analyst provider degraded.")
        return None

    full_params = {**params, "token": key}
    url = f"{_FINNHUB_BASE}{path}"

    backoff = _FINNHUB_BACKOFF_BASE
    for attempt in range(_FINNHUB_MAX_RETRIES + 1):
        _throttle()
        try:
            resp = requests.get(
                url, params=full_params, timeout=_FINNHUB_TIMEOUT
            )
        except requests.RequestException as exc:
            logger.warning(
                "Finnhub %s transport error (attempt %d): %s",
                path,
                attempt + 1,
                exc,
            )
            if attempt == _FINNHUB_MAX_RETRIES:
                return None
            time.sleep(backoff)
            backoff *= 2
            continue

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                logger.warning("Finnhub %s bad JSON: %s", path, exc)
                return None

        if resp.status_code in _RETRIABLE_STATUS:
            logger.info(
                "Finnhub %s HTTP %d — sleeping %.1fs (attempt %d/%d).",
                path,
                resp.status_code,
                backoff,
                attempt + 1,
                _FINNHUB_MAX_RETRIES + 1,
            )
            if attempt == _FINNHUB_MAX_RETRIES:
                logger.warning(
                    "Finnhub %s HTTP %d — retries exhausted, "
                    "falling back to yfinance.",
                    path,
                    resp.status_code,
                )
                return None
            time.sleep(backoff)
            backoff *= 2
            continue

        logger.warning(
            "Finnhub %s HTTP %d — giving up.", path, resp.status_code
        )
        return None

    return None


# ── Net upgrades (rating drift) ────────────────────────────────────────────


def _net_upgrades_30d(ticker: str) -> int:
    """Net upgrades minus downgrades in the last 30 days.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        ``upgrades − downgrades`` filtered to the last 30 days; ``0`` on
        any error or empty payload.
    """
    payload = _finnhub_get("/stock/upgrade-downgrade", {"symbol": ticker})
    if not isinstance(payload, list):
        return 0

    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(
        days=_RATING_DRIFT_WINDOW_DAYS
    )
    cutoff_ts = int(cutoff.timestamp())

    upgrades = 0
    downgrades = 0
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        ts = entry.get("gradeTime")
        if not isinstance(ts, (int, float)) or int(ts) < cutoff_ts:
            continue
        action = str(entry.get("action", "")).lower()
        if action == "up":
            upgrades += 1
        elif action == "down":
            downgrades += 1
    return upgrades - downgrades


# ── Recommendation snapshot ────────────────────────────────────────────────


def _recommendation(ticker: str) -> tuple[int, int, int]:
    """Return ``(strong_buy, buy, total)`` from the most recent snapshot.

    Falls back to ``(0, 0, 0)`` when the provider returns nothing.
    """
    payload = _finnhub_get("/stock/recommendation", {"symbol": ticker})
    if not isinstance(payload, list) or not payload:
        return 0, 0, 0
    # Finnhub returns the list ordered with most recent first.
    latest = payload[0]
    if not isinstance(latest, dict):
        return 0, 0, 0
    sb = _coerce_int(latest.get("strongBuy"))
    b = _coerce_int(latest.get("buy"))
    h = _coerce_int(latest.get("hold"))
    s = _coerce_int(latest.get("sell"))
    ss = _coerce_int(latest.get("strongSell"))
    total = sb + b + h + s + ss
    return sb, b, total


def _recommendation_with_drift(
    ticker: str,
) -> tuple[int, int, int, int]:
    """Return ``(strong_buy, buy, total, net_drift)`` from recommendation.

    Makes a single ``/stock/recommendation`` call and derives both the
    current consensus counts *and* the month-over-month bullish drift,
    eliminating the separate ``/stock/upgrade-downgrade`` call.

    ``net_drift`` is ``(sb[0] + b[0]) − (sb[1] + b[1])``: the change in
    bullish analyst count between the most recent and prior monthly
    snapshot.  This approximates net upgrades for the Rating Drift signal;
    accuracy is within 1–2 analysts vs. the exact 30-day event count.

    # Alternatives considered:
    # - Keep _net_upgrades_30d (/stock/upgrade-downgrade): more precise
    #   (exact events in 30 days) but adds a third Finnhub call per ticker.
    #   On a 511-ticker universe at 60 calls/min, the third call costs an
    #   extra ~8.5 minutes wall-clock time. Month-over-month delta from the
    #   already-fetched /stock/recommendation payload is a close proxy.
    # - yfinance upgrades_downgrades for drift in Finnhub path: already
    #   used in _analyst_from_yfinance; mixing sources within the Finnhub
    #   path would make the signal non-comparable across runs.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        Tuple of ``(strong_buy, buy, total, net_drift)``; all zero when
        the provider returns nothing.
    """
    payload = _finnhub_get("/stock/recommendation", {"symbol": ticker})
    if not isinstance(payload, list) or not payload:
        return 0, 0, 0, 0
    latest = payload[0]
    if not isinstance(latest, dict):
        return 0, 0, 0, 0
    sb = _coerce_int(latest.get("strongBuy"))
    b = _coerce_int(latest.get("buy"))
    h = _coerce_int(latest.get("hold"))
    s = _coerce_int(latest.get("sell"))
    ss = _coerce_int(latest.get("strongSell"))
    total = sb + b + h + s + ss
    net_drift = 0
    if len(payload) > 1:
        prev = payload[1]
        if isinstance(prev, dict):
            prev_sb = _coerce_int(prev.get("strongBuy"))
            prev_b = _coerce_int(prev.get("buy"))
            net_drift = (sb + b) - (prev_sb + prev_b)
    return sb, b, total, net_drift


def _coerce_int(value: object) -> int:
    """Best-effort int coercion; ``0`` on anything weird."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


# ── Price target ───────────────────────────────────────────────────────────


def _price_target(ticker: str) -> float | None:
    """Mean analyst price target; ``None`` if unavailable."""
    payload = _finnhub_get("/stock/price-target", {"symbol": ticker})
    if not isinstance(payload, dict):
        return None
    raw = payload.get("targetMean")
    if isinstance(raw, (int, float)) and raw > 0:
        return float(raw)
    return None


# ── EPS revision slope (yfinance) ──────────────────────────────────────────

_EPS_TREND_PERIODS: tuple[str, ...] = (
    "7daysAgo",
    "30daysAgo",
    "60daysAgo",
    "90daysAgo",
)


def _eps_revision_slope(ticker: str) -> float:
    """Mean fractional revision of forward-quarter EPS estimates.

    For the nearest forecast quarter, compares the *current* consensus
    estimate to its 7d / 30d / 60d / 90d historical snapshots and
    returns the mean fractional difference. Positive = upward revisions
    over the trailing 90 days.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        Slope as a decimal (e.g. ``0.05`` = +5% mean revision); ``0.0``
        on missing or unparseable data.
    """
    try:
        trend = yf.Ticker(ticker).get_eps_trend()
    except Exception as exc:
        logger.debug("eps_trend fetch failed for %s: %s", ticker, exc)
        return 0.0

    if not isinstance(trend, pd.DataFrame) or trend.empty:
        return 0.0
    row = trend.iloc[0]
    if "current" not in row.index:
        return 0.0
    try:
        current = float(row["current"])
    except (TypeError, ValueError):
        return 0.0

    deltas: list[float] = []
    for period in _EPS_TREND_PERIODS:
        if period not in row.index:
            continue
        try:
            past = float(row[period])
        except (TypeError, ValueError):
            continue
        if past == 0:
            continue
        deltas.append((current - past) / abs(past))

    if not deltas:
        return 0.0
    return sum(deltas) / len(deltas)


# ── yfinance fallback ──────────────────────────────────────────────────────


def _analyst_from_yfinance(
    ticker: str,
) -> tuple[int, int, int, int, float | None]:
    """Pull analyst consensus from yfinance as Finnhub fallback.

    Uses ``recommendations_summary`` for counts and
    ``analyst_price_targets`` for the mean target.  Upgrades/downgrades
    are derived from ``upgrades_downgrades`` filtered to 30 days.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        ``(net_upgrades, strong_buy, buy, total, target_mean_price)``
        — any field is ``0`` / ``None`` when data is unavailable.
    """
    t = yf.Ticker(ticker)
    net_upgrades = 0
    strong_buy = 0
    buy_ct = 0
    total = 0
    target: float | None = None

    try:
        targets = t.analyst_price_targets
        if isinstance(targets, dict):
            raw = targets.get("mean")
            if isinstance(raw, (int, float)) and float(raw) > 0:
                target = float(raw)
    except Exception as exc:
        logger.debug(
            "yfinance analyst_price_targets failed for %s: %s", ticker, exc
        )

    try:
        rec = t.recommendations_summary
        if isinstance(rec, pd.DataFrame) and not rec.empty:
            if "period" in rec.columns:
                current = rec[rec["period"] == "0m"]
            else:
                current = rec.head(1)
            if not current.empty:
                row = current.iloc[0]
                strong_buy = int(
                    row.get("strongBuy", 0)
                    if hasattr(row, "get")
                    else row["strongBuy"]
                    if "strongBuy" in row.index
                    else 0
                )
                buy_ct = int(
                    row.get("buy", 0)
                    if hasattr(row, "get")
                    else row["buy"]
                    if "buy" in row.index
                    else 0
                )
                hold = int(
                    row.get("hold", 0)
                    if hasattr(row, "get")
                    else row["hold"]
                    if "hold" in row.index
                    else 0
                )
                sell = int(
                    row.get("sell", 0)
                    if hasattr(row, "get")
                    else row["sell"]
                    if "sell" in row.index
                    else 0
                )
                strong_sell = int(
                    row.get("strongSell", 0)
                    if hasattr(row, "get")
                    else row["strongSell"]
                    if "strongSell" in row.index
                    else 0
                )
                total = strong_buy + buy_ct + hold + sell + strong_sell
    except Exception as exc:
        logger.debug(
            "yfinance recommendations_summary failed for %s: %s", ticker, exc
        )

    try:
        ud = t.upgrades_downgrades
        if isinstance(ud, pd.DataFrame) and not ud.empty:
            cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=30)
            recent = ud[ud.index >= cutoff]
            if "Action" in recent.columns:
                actions = recent["Action"].str.lower()
                net_upgrades = int(
                    (actions == "up").sum() - (actions == "down").sum()
                )
    except Exception as exc:
        logger.debug(
            "yfinance upgrades_downgrades failed for %s: %s", ticker, exc
        )

    return net_upgrades, strong_buy, buy_ct, total, target


# ── Public entry point ─────────────────────────────────────────────────────


def fetch_analyst_snapshot(ticker: str) -> AnalystSnapshot:
    """Fetch every analyst-driven field for ``ticker``.

    Primary source: Finnhub API (requires ``FINNHUB_API_KEY``).
    Fallback source: yfinance ``recommendations_summary``,
    ``analyst_price_targets``, and ``upgrades_downgrades``.

    The fallback activates when: (a) no Finnhub key is set, or (b)
    Finnhub returns no usable data (all zeros/None) for the ticker.

    EPS revision slope always uses yfinance ``get_eps_trend()`` —
    there is no equivalent free Finnhub endpoint.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        Fully populated :class:`AnalystSnapshot`.
    """
    key_present = _api_key() is not None

    if key_present:
        logger.info("analyst | %-6s | Finnhub API (2 calls)", ticker)
        try:
            sb, b, total, net = _recommendation_with_drift(ticker)
        except Exception as exc:
            logger.warning(
                "Finnhub recommendation failed for %s: %s", ticker, exc
            )
            sb, b, total, net = 0, 0, 0, 0
        try:
            target = _price_target(ticker)
        except Exception as exc:
            logger.warning(
                "Finnhub price_target failed for %s: %s", ticker, exc
            )
            target = None

        # If Finnhub returned nothing useful, fall through to yfinance.
        if total == 0 and target is None and net == 0:
            logger.info(
                "analyst | %-6s | Finnhub empty → yfinance fallback",
                ticker,
            )
            net, sb, b, total, target = _analyst_from_yfinance(ticker)
    else:
        logger.info(
            "analyst | %-6s | no Finnhub key → yfinance fallback", ticker
        )
        net, sb, b, total, target = _analyst_from_yfinance(ticker)

    try:
        slope = _eps_revision_slope(ticker)
    except Exception as exc:
        logger.warning("eps_revision_slope failed for %s: %s", ticker, exc)
        slope = 0.0

    return AnalystSnapshot(
        ticker=ticker,
        net_upgrades_30d=net,
        eps_revision_slope=slope,
        target_mean_price=target,
        analyst_count=total,
        strong_buy_count=sb,
        buy_count=b,
    )
