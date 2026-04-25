"""Dual-Track filtering engine for AlphaVision equity candidates."""

from __future__ import annotations

import logging

from alphavision.models import TickerData

# Alternatives considered:
# - Single-channel filter: misses value AND momentum opportunities; the
#   Dual-Track is specifically designed to capture both regimes simultaneously.
# - Quantile-based thresholds: more adaptive but non-deterministic across runs
#   and hard to explain; fixed thresholds from METADOLOGY.md are auditable.
# - Industry-specific thresholds: adds complexity without MVP benefit.

logger = logging.getLogger(__name__)

TURNAROUND_DRAWDOWN_THRESHOLD: float = -0.25  # Channel A: ≥25% from peak
MOMENTUM_SMA_MULTIPLIER: float = 1.0  # Channel B: price > N × SMA200
MOMENTUM_RETURN_THRESHOLD: float = 0.0  # Channel B: 6m return > 0


def passes_turnaround(data: TickerData) -> bool:
    """Channel A: stock has declined ≥25% from its 6-month peak.

    Args:
        data: TickerData snapshot for a single ticker.

    Returns:
        True if drawdown_pct <= TURNAROUND_DRAWDOWN_THRESHOLD (-0.25).
    """
    return data.drawdown_pct <= TURNAROUND_DRAWDOWN_THRESHOLD


def passes_momentum(data: TickerData) -> bool:
    """Channel B: price above SMA-200 AND positive 6-month return.

    Args:
        data: TickerData snapshot for a single ticker.

    Returns:
        True if current_price > sma_200 × MOMENTUM_SMA_MULTIPLIER
        AND return_6m > MOMENTUM_RETURN_THRESHOLD.
    """
    return (
        data.current_price > data.sma_200 * MOMENTUM_SMA_MULTIPLIER
        and data.return_6m > MOMENTUM_RETURN_THRESHOLD
    )


def apply_dual_track(universe: list[TickerData]) -> list[TickerData]:
    """Return tickers that pass Channel A (Turnaround) OR Channel B (Momentum).

    Tickers qualifying for both channels are included once.
    Input order is preserved among candidates.

    Args:
        universe: Full list of TickerData to evaluate.

    Returns:
        Filtered list of TickerData; subset of the input universe.
    """
    result = [
        d for d in universe if passes_turnaround(d) or passes_momentum(d)
    ]
    logger.info(
        "Dual-Track filter: %d of %d tickers passed.",
        len(result),
        len(universe),
    )
    return result
