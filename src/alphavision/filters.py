"""Forward-Momentum entry gate for AlphaVision (v3.0)."""

from __future__ import annotations

import logging

from alphavision.models import TickerData

# Alternatives considered:
# - Dual-Track (v2.0) Channel A + B: Channel A (drawdown ≥ 25%) recruits
#   "Fallen Angel" tickers whose only edge is a stale analyst target divided
#   by a depressed price. With a 6-month forward horizon this is mean
#   reversion, not momentum, and was the structural source of v2.0's bias.
# - Quantile gates (top-decile RS): non-deterministic across runs and
#   harder to explain; fixed thresholds remain auditable.
# - Industry-specific gates: adds complexity without MVP-phase benefit.

logger = logging.getLogger(__name__)

SMA_200_MULTIPLIER: float = 1.0
"""Gate 1: ``current_price > SMA_200_MULTIPLIER × sma_200``."""

RETURN_12_1_THRESHOLD: float = 0.0
"""Gate 2: ``return_12_1 > RETURN_12_1_THRESHOLD``."""

EXTENSION_CAP: float = 1.15
"""Gate 3: ``current_price ≤ EXTENSION_CAP × sma_20``."""

MIN_ANALYST_COUNT: int = 3
"""Gate 4: ``analyst_count ≥ MIN_ANALYST_COUNT``."""


def passes_forward_momentum(data: TickerData) -> bool:
    """Return True iff the ticker passes all four forward-momentum gates.

    Gates (must pass ALL):
        1. ``current_price > sma_200`` — long-term uptrend confirmed.
        2. ``return_12_1 > 0`` — positive intermediate-horizon momentum,
           computed over the canonical Jegadeesh-Titman 12-1 window.
        3. ``current_price ≤ 1.15 × sma_20`` — price has not blown off
           too far above its 20-day average; prevents chasing climactic
           tops where mean-reversion risk is acute.
        4. ``analyst_count ≥ 3`` — minimum coverage so analyst-driven
           sub-scores are statistically meaningful. When ``analyst_count``
           is ``0`` the data is treated as unavailable (Finnhub not
           configured) and the gate is bypassed to preserve graceful
           degradation.

    Args:
        data: TickerData snapshot for a single ticker.

    Returns:
        True iff all four gates pass.
    """
    if data.sma_200 <= 0 or data.sma_20 <= 0:
        return False
    # analyst_count == 0 means "no data fetched" (e.g. Finnhub key absent),
    # not "truly zero analysts". Treat as unknown — do not block the ticker.
    analyst_ok = (
        data.analyst_count == 0 or data.analyst_count >= MIN_ANALYST_COUNT
    )
    return (
        data.current_price > data.sma_200 * SMA_200_MULTIPLIER
        and data.return_12_1 > RETURN_12_1_THRESHOLD
        and data.current_price <= EXTENSION_CAP * data.sma_20
        and analyst_ok
    )


def apply_forward_momentum(universe: list[TickerData]) -> list[TickerData]:
    """Return tickers that pass the Forward-Momentum gate, in input order.

    Args:
        universe: Full list of TickerData to evaluate.

    Returns:
        Filtered list of TickerData; subset of the input universe.
    """
    result = [d for d in universe if passes_forward_momentum(d)]
    logger.info(
        "Forward-Momentum filter: %d of %d tickers passed.",
        len(result),
        len(universe),
    )
    return result
