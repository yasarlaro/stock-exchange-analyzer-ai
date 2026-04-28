"""Per-ticker orchestrator over the provider package.

Composes a :class:`TickerData` from three independent providers:

- :mod:`alphavision.providers.prices`       — yfinance ``history()``
- :mod:`alphavision.providers.analyst`      — Finnhub + yfinance fallback
- :mod:`alphavision.providers.fundamentals` — SEC EDGAR + yfinance fallback

Each provider's failures are isolated: a transient error in one source
yields neutral defaults but does not drop the row.

:func:`probe_providers` can be called before the full universe fetch to
surface which providers are configured, so the UI can warn the user
about degraded signals before the expensive run starts.

:func:`fetch_universe_two_phase` is the optimised full-universe path:

  Phase 1 — ``yf.download()`` batch-fetches all prices in one session
  (seconds), then applies the three price-based momentum gates to reduce
  the universe by ~55–65%.

  Phase 2 — analyst (2 Finnhub calls) + EDGAR run only for the ~35–45%
  that survived, in parallel.

  For 511 tickers on the free Finnhub tier (60 calls/min):
  - Old ``fetch_universe``:          ~60 min (3 Finnhub calls × 511)
  - ``fetch_universe_two_phase``:    ~7–8 min (2 Finnhub calls × ~200)

# Alternatives considered:
# - Inline yfinance calls (v3.0): worked, but `Ticker.info` 404s for ETFs
#   and the analyst sub-fields had spotty coverage; isolating providers
#   makes each failure mode independently observable and replaceable.
# - Async orchestration (asyncio + aiohttp): yfinance and edgartools are
#   synchronous; ThreadPoolExecutor gives I/O concurrency without rewriting
#   them.
# - Per-provider rate-limit handling in a shared layer: each provider has
#   different limits (yfinance ~1-2 req/s burst; Finnhub 60/min; EDGAR
#   10/s). A shared limiter would have to be the strictest, wasting
#   throughput on yfinance and EDGAR.
# - More workers (>3): does not help Finnhub — _throttle_lock serialises
#   every Finnhub call regardless of worker count.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from alphavision.filters import (
    EXTENSION_CAP,
    RETURN_12_1_THRESHOLD,
    SMA_200_MULTIPLIER,
)
from alphavision.models import TickerData
from alphavision.providers.analyst import (
    AnalystSnapshot,
    fetch_analyst_snapshot,
)
from alphavision.providers.fundamentals import (
    _EDGAR_IDENTITY_ENV,
    FundamentalsSnapshot,
    fetch_fundamentals_snapshot,
)
from alphavision.providers.prices import (
    PriceSnapshot,
    fetch_benchmark_return_12_1,
    fetch_price_batch,
    fetch_price_snapshot,
    is_rate_limited,
)

# ── Provider status ────────────────────────────────────────────────────────


@dataclass
class ProviderStatus:
    """Availability summary for each data provider.

    Produced by :func:`probe_providers` before the full universe fetch.
    The UI uses this to warn the user about degraded signals.

    Attributes:
        prices_source: Always ``"yfinance"`` (only provider available).
        analyst_source: ``"finnhub"`` when the API key is set, else
            ``"yfinance"`` (reduced accuracy fallback).
        fundamentals_source: ``"edgar"`` — EDGAR always has a default
            identity; custom identity improves rate-limit headroom.
        finnhub_key_set: ``True`` iff ``FINNHUB_API_KEY`` is in env.
        edgar_identity_custom: ``True`` iff ``EDGAR_IDENTITY`` is
            explicitly set (custom identity vs. generic default).
        warnings: Human-readable lines describing degraded conditions.
    """

    prices_source: str = "yfinance"
    analyst_source: str = "finnhub"
    fundamentals_source: str = "edgar"
    finnhub_key_set: bool = False
    edgar_identity_custom: bool = False
    warnings: list[str] = field(default_factory=list)


logger = logging.getLogger(__name__)

_DEFAULT_MAX_WORKERS: int = 3
_BENCHMARK_TICKER: str = "SPY"

_RATE_LIMIT_COOLDOWN: float = 8.0
_MAX_RETRY_ROUNDS: int = 10


def probe_providers() -> ProviderStatus:
    """Detect which data providers are configured without making API calls.

    Reads environment variables to determine which providers will be used
    and generates human-readable warnings for any degraded conditions.
    No network I/O is performed — this is safe to call before the UI
    presents a confirmation dialog.

    Returns:
        :class:`ProviderStatus` describing what each provider will use
        and any associated warnings.
    """
    from alphavision.providers.analyst import _FINNHUB_API_KEY_ENV

    finnhub_key = os.environ.get(_FINNHUB_API_KEY_ENV, "").strip()
    edgar_identity = os.environ.get(_EDGAR_IDENTITY_ENV, "").strip()

    finnhub_set = bool(finnhub_key)
    edgar_custom = bool(edgar_identity)

    analyst_source = "finnhub" if finnhub_set else "yfinance"
    warnings: list[str] = []

    if not finnhub_set:
        warnings.append(
            "FINNHUB_API_KEY not set — analyst signals (Rating Drift, "
            "Consensus) will use yfinance fallback data (reduced accuracy)."
        )
    if not edgar_custom:
        warnings.append(
            "EDGAR_IDENTITY not set — using generic SEC identity. "
            "Set EDGAR_IDENTITY in .env to improve rate-limit headroom."
        )

    return ProviderStatus(
        prices_source="yfinance",
        analyst_source=analyst_source,
        fundamentals_source="edgar",
        finnhub_key_set=finnhub_set,
        edgar_identity_custom=edgar_custom,
        warnings=warnings,
    )


def _passes_price_gate(snap: PriceSnapshot) -> bool:
    """Return True iff ``snap`` passes the three price-based momentum gates.

    Applies gates 1 (price > SMA-200), 2 (12-1 return > 0), and 3
    (price ≤ 1.15 × SMA-20) using the filter constants from
    :mod:`alphavision.filters`.  Gate 4 (analyst_count ≥ 3) is deferred
    to :func:`alphavision.filters.apply_forward_momentum` after Phase 2
    data is available.

    Args:
        snap: PriceSnapshot from the Phase 1 batch download.

    Returns:
        True iff all three price-based gates pass.
    """
    if snap.sma_200 <= 0 or snap.sma_20 <= 0:
        return False
    return (
        snap.current_price > snap.sma_200 * SMA_200_MULTIPLIER
        and snap.return_12_1 > RETURN_12_1_THRESHOLD
        and snap.current_price <= EXTENSION_CAP * snap.sma_20
    )


def _fetch_analyst_and_fundamentals(
    ticker: str,
    price: PriceSnapshot,
) -> TickerData:
    """Build :class:`TickerData` from an existing price snapshot.

    Phase 2 helper for :func:`fetch_universe_two_phase`: price data was
    already fetched in bulk during Phase 1, so only the analyst and
    fundamentals providers need to be called.

    Failures in either provider are caught and replaced with neutral
    defaults so a single weak source does not drop the row.

    Args:
        ticker: Stock ticker symbol.
        price: Pre-fetched :class:`PriceSnapshot` from Phase 1.

    Returns:
        Fully populated :class:`TickerData` with
        ``relative_strength_12_1 = 0.0`` (set by the caller).
    """
    logger.info("fetch   | %-6s | phase-2 (analyst+fundamentals)", ticker)
    try:
        analyst: AnalystSnapshot = fetch_analyst_snapshot(ticker)
    except Exception as exc:
        logger.warning(
            "Analyst failed for %s; using defaults: %s", ticker, exc
        )
        analyst = AnalystSnapshot(ticker=ticker)

    try:
        fundamentals: FundamentalsSnapshot = fetch_fundamentals_snapshot(
            ticker
        )
    except Exception as exc:
        logger.warning(
            "Fundamentals failed for %s; using defaults: %s", ticker, exc
        )
        fundamentals = FundamentalsSnapshot(ticker=ticker)

    return TickerData(
        ticker=ticker,
        company=price.company,
        current_price=price.current_price,
        sma_20=price.sma_20,
        sma_200=price.sma_200,
        return_12_1=price.return_12_1,
        target_mean_price=analyst.target_mean_price,
        analyst_count=analyst.analyst_count,
        strong_buy_count=analyst.strong_buy_count,
        buy_count=analyst.buy_count,
        net_upgrades_30d=analyst.net_upgrades_30d,
        eps_revision_slope=analyst.eps_revision_slope,
        rule_of_40=fundamentals.rule_of_40,
        earnings_quality=fundamentals.earnings_quality,
    )


def fetch_universe_two_phase(
    tickers: list[str],
    company_lookup: dict[str, str] | None = None,
    max_workers: int = _DEFAULT_MAX_WORKERS,
    status_fn: Callable[[str], None] | None = None,
) -> tuple[list[TickerData], int]:
    """Two-phase fetch: bulk price pre-filter, then analyst+fundamentals.

    Phase 1 (seconds): ``yf.download()`` fetches all price history in one
    batched session, then the three price-based momentum gates reduce the
    universe by ~55–65%.

    Phase 2 (~7–8 min on 511 tickers, free Finnhub tier): analyst (2
    Finnhub calls via ``_recommendation_with_drift`` + ``/price-target``)
    and EDGAR run only for price-gate survivors, in parallel threads.

    Combined, Finnhub calls drop from ``3 × N`` to ``2 × 0.40 × N``,
    cutting analysis time from ~60 min to ~7–8 min on the full universe.

    Args:
        tickers: Stock ticker symbols for the full universe.
        company_lookup: Optional ``{ticker: company_name}`` mapping used
            to populate ``PriceSnapshot.company`` without an extra
            ``Ticker.info`` call per ticker.
        max_workers: Concurrent fetch threads for Phase 2 (default ``3``).
        status_fn: Optional UI callback for progress messages.

    Returns:
        Tuple of ``(ticker_data_list, total_scanned)`` where
        ``ticker_data_list`` contains :class:`TickerData` for all
        price-gate survivors (in input order, with
        ``relative_strength_12_1`` populated), and ``total_scanned`` is
        the full input length before pre-filtering.
    """
    if not tickers:
        return [], 0

    total_scanned = len(tickers)

    def _notify(msg: str) -> None:
        logger.info(msg)
        if status_fn is not None:
            status_fn(msg)

    # ── Phase 1: batch price fetch + pre-filter ────────────────────────────
    _notify(f"Phase 1: batch price-fetching {total_scanned} tickers…")
    price_batch = fetch_price_batch(tickers, company_lookup=company_lookup)
    _notify(
        f"Phase 1 complete: {len(price_batch)} price snapshots. "
        "Applying price gate (SMA-200, 12-1 return, extension cap)…"
    )

    survivors: list[tuple[int, str]] = [
        (i, t)
        for i, t in enumerate(tickers)
        if t in price_batch and _passes_price_gate(price_batch[t])
    ]
    _notify(
        f"Price gate: {len(survivors)} of {len(price_batch)} tickers "
        "advance to Phase 2 (analyst + fundamentals)."
    )

    if not survivors:
        return [], total_scanned

    # ── Phase 2: analyst + fundamentals for survivors ──────────────────────
    results: dict[int, TickerData] = {}
    skipped = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_key: dict[Future[TickerData], tuple[int, str]] = {
            executor.submit(
                _fetch_analyst_and_fundamentals,
                ticker,
                price_batch[ticker],
            ): (idx, ticker)
            for idx, ticker in survivors
        }

        done = 0
        total_phase2 = len(survivors)
        for future in as_completed(future_to_key):
            idx, ticker = future_to_key[future]
            done += 1
            try:
                results[idx] = future.result()
                if done % 20 == 0 or done == total_phase2:
                    _notify(
                        f"Phase 2: {done}/{total_phase2} "
                        "analyst+fundamentals fetched…"
                    )
            except Exception as exc:
                skipped += 1
                logger.warning(
                    "Skipping '%s' (permanent error): %s", ticker, exc
                )

    all_results = [results[i] for i in sorted(results)]
    _notify(
        f"Phase 2 complete: {len(all_results)} tickers "
        f"({skipped} skipped). Fetching SPY benchmark…"
    )

    benchmark = fetch_benchmark_return_12_1(_BENCHMARK_TICKER)
    logger.info("SPY benchmark 12-1 return: %.4f", benchmark)
    scored = [
        r.model_copy(
            update={"relative_strength_12_1": r.return_12_1 - benchmark}
        )
        for r in all_results
    ]
    return scored, total_scanned


def fetch_ticker(ticker: str) -> TickerData:
    """Compose a :class:`TickerData` for ``ticker`` from all providers.

    The price provider runs first and is the only one that can raise:
    a missing or too-short price history makes the ticker fundamentally
    unscoreable. The analyst and fundamentals providers degrade
    gracefully — failures yield neutral defaults so a single weak source
    does not drop the row.

    Args:
        ticker: Stock ticker symbol (e.g. ``"AAPL"``).

    Returns:
        Fully populated :class:`TickerData` with
        ``relative_strength_12_1 = 0.0`` (set by ``fetch_universe``).

    Raises:
        ValueError: If price history is missing or too short.
    """
    logger.info("fetch   | %-6s | starting", ticker)
    price = fetch_price_snapshot(ticker)

    try:
        analyst: AnalystSnapshot = fetch_analyst_snapshot(ticker)
    except Exception as exc:
        logger.warning(
            "Analyst provider failed for %s; using defaults: %s", ticker, exc
        )
        analyst = AnalystSnapshot(ticker=ticker)

    try:
        fundamentals: FundamentalsSnapshot = fetch_fundamentals_snapshot(
            ticker
        )
    except Exception as exc:
        logger.warning(
            "Fundamentals provider failed for %s; using defaults: %s",
            ticker,
            exc,
        )
        fundamentals = FundamentalsSnapshot(ticker=ticker)

    return TickerData(
        ticker=ticker,
        company=price.company,
        current_price=price.current_price,
        sma_20=price.sma_20,
        sma_200=price.sma_200,
        return_12_1=price.return_12_1,
        target_mean_price=analyst.target_mean_price,
        analyst_count=analyst.analyst_count,
        strong_buy_count=analyst.strong_buy_count,
        buy_count=analyst.buy_count,
        net_upgrades_30d=analyst.net_upgrades_30d,
        eps_revision_slope=analyst.eps_revision_slope,
        rule_of_40=fundamentals.rule_of_40,
        earnings_quality=fundamentals.earnings_quality,
    )


def fetch_universe(
    tickers: list[str],
    max_workers: int = _DEFAULT_MAX_WORKERS,
    status_fn: Callable[[str], None] | None = None,
) -> list[TickerData]:
    """Fetch all tickers, retrying rate-limited ones until none remain.

    Multi-round batch strategy: each round runs all pending tickers in
    parallel; those that hit the price provider's rate limit are
    collected and retried after a growing cooldown. Permanent errors
    (e.g. delisted ticker, no price history) drop the row immediately.
    Input order is preserved.

    Args:
        tickers: Stock ticker symbols.
        max_workers: Maximum concurrent fetch threads (default ``3``).
        status_fn: Optional callback called with a progress message after
            each completed batch. Useful for streaming updates to a UI.

    Returns:
        List of :class:`TickerData` in input order with
        ``relative_strength_12_1`` populated.
    """
    if not tickers:
        return []

    def _notify(msg: str) -> None:
        logger.info(msg)
        if status_fn is not None:
            status_fn(msg)

    _notify(
        f"Starting universe fetch: {len(tickers)} tickers, "
        f"{max_workers} parallel workers."
    )

    results: dict[int, TickerData] = {}
    pending: list[tuple[int, str]] = list(enumerate(tickers))
    skipped: int = 0

    for round_num in range(_MAX_RETRY_ROUNDS):
        if not pending:
            break

        rate_limited: list[tuple[int, str]] = []
        round_ok = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx: dict[Future[TickerData], tuple[int, str]] = {
                executor.submit(fetch_ticker, ticker): (idx, ticker)
                for idx, ticker in pending
            }
            for future in as_completed(future_to_idx):
                idx, ticker = future_to_idx[future]
                try:
                    results[idx] = future.result()
                    round_ok += 1
                except Exception as exc:
                    if is_rate_limited(exc):
                        rate_limited.append((idx, ticker))
                    else:
                        skipped += 1
                        logger.warning(
                            "Skipping '%s' (permanent error): %s",
                            ticker,
                            exc,
                        )

        pending = rate_limited
        fetched_total = len(results)

        if not pending:
            _notify(
                f"Round {round_num + 1}: done. "
                f"{fetched_total} fetched, {skipped} skipped."
            )
            break

        cooldown = _RATE_LIMIT_COOLDOWN * (round_num + 1)
        _notify(
            f"Round {round_num + 1}: {fetched_total} fetched so far, "
            f"{len(pending)} rate-limited — retrying in {cooldown:.0f}s."
        )
        time.sleep(cooldown)

    if pending:
        logger.warning(
            "Exhausted %d retry rounds; %d tickers still rate-limited "
            "and will be omitted: %s",
            _MAX_RETRY_ROUNDS,
            len(pending),
            [t for _, t in pending],
        )
        if status_fn is not None:
            status_fn(
                f"Warning: {len(pending)} tickers omitted after "
                f"{_MAX_RETRY_ROUNDS} retry rounds."
            )

    all_results = [results[i] for i in sorted(results)]
    _notify(
        f"Fetched {len(all_results)} tickers successfully "
        f"({skipped} skipped). Fetching SPY benchmark…"
    )

    benchmark = fetch_benchmark_return_12_1(_BENCHMARK_TICKER)
    logger.info("SPY benchmark 12-1 return: %.4f", benchmark)
    return [
        r.model_copy(
            update={"relative_strength_12_1": r.return_12_1 - benchmark}
        )
        for r in all_results
    ]
