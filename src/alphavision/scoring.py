"""Forward-Momentum Conviction Score engine (v3.0)."""

from __future__ import annotations

import logging

from alphavision.models import ScoredTicker, TickerData

# Alternatives considered:
# - v2.0 weights (Upside 35% / Drift 25% / RS 15% / Consensus 15% / EPS 10%):
#   75% sell-side weight + 35% Upside Gap mechanically rewarded drawdowns,
#   pushing "Fallen Angels" to the top. v3.0 flips the ratio: forward-looking
#   factors total 70% and sell-side 30%.
# - Rating Drift as Strong-Buy *fraction* (v3.0 first cut): a static fraction
#   does not measure drift; replaced with the count of net upgrades over the
#   last 30 days, which is what the methodology actually claims to capture.
# - EPS Revision as a single (current vs 30d) delta: too noisy on a single
#   data point. The slope formula averages the fractional revision across
#   four lookback windows (7d, 30d, 60d, 90d).

logger = logging.getLogger(__name__)

WEIGHTS: dict[str, float] = {
    "relative_strength": 0.30,
    "eps_revision": 0.25,
    "rating_drift": 0.15,
    "trend_quality": 0.15,
    "upside_gap": 0.10,
    "consensus_strength": 0.05,
}

_TOP_N: int = 20

# ── Normalisation constants ─────────────────────────────────────────────────

_RS_SCALE: float = 200.0
"""±25% of 12-1 outperformance vs. SPY → ±50 sub-score swing."""

_EPS_SCALE: float = 500.0
"""±10% mean EPS revision → ±50 sub-score swing."""

_TREND_SCALE: float = 200.0
"""+25% above SMA-200 → +50 sub-score swing (max 100 at 1.25× SMA-200)."""

_UPSIDE_CAP: float = 0.30
"""30% analyst upside → sub-score 100."""

_RATING_DRIFT_PER_NET_UPGRADE: float = 10.0
"""Each net upgrade in the last 30d adds 10 pts above neutral 50.

5 net upgrades → 100; 5 net downgrades → 0.
"""

# ── Stress-test penalty ────────────────────────────────────────────────────

_EXTENSION_PENALTY_THRESHOLD: float = 0.10
_EXTENSION_PENALTY_FACTOR: float = 0.90


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp value to ``[lo, hi]``."""
    return max(lo, min(hi, value))


def _relative_strength_score(data: TickerData) -> float:
    """12-1 relative-strength sub-score in ``[0, 100]``, centred at 50."""
    return _clamp(50.0 + data.relative_strength_12_1 * _RS_SCALE)


def _eps_revision_score(data: TickerData) -> float:
    """EPS revision-slope sub-score in ``[0, 100]``, centred at 50.

    The slope is the *mean fractional revision* of forward EPS estimates
    over the trailing 7 / 30 / 60 / 90 day windows; positive values
    indicate upward revisions.
    """
    return _clamp(50.0 + data.eps_revision_slope * _EPS_SCALE)


def _rating_drift_score(data: TickerData) -> float:
    """Net-upgrades sub-score in ``[0, 100]``, centred at 50.

    Each net upgrade in the last 30 days adds
    ``_RATING_DRIFT_PER_NET_UPGRADE`` points above 50; each net downgrade
    subtracts the same amount. Saturates at 0 / 100.
    """
    return _clamp(50.0 + data.net_upgrades_30d * _RATING_DRIFT_PER_NET_UPGRADE)


def _trend_quality_score(data: TickerData) -> float:
    """Price-above-SMA200 sub-score in ``[0, 100]``, centred at 50."""
    if data.sma_200 <= 0:
        return 0.0
    deviation = data.current_price / data.sma_200 - 1.0
    return _clamp(50.0 + deviation * _TREND_SCALE)


def _upside_gap_score(data: TickerData) -> float:
    """Analyst-target upside sub-score in ``[0, 100]``."""
    if data.target_mean_price is None or data.current_price <= 0:
        return 0.0
    upside = data.target_mean_price / data.current_price - 1.0
    return _clamp(upside / _UPSIDE_CAP * 100.0)


def _consensus_strength_score(data: TickerData) -> float:
    """Strong-Buy + Buy fraction sub-score in ``[0, 100]``."""
    if data.analyst_count <= 0:
        return 0.0
    ratio = (data.strong_buy_count + data.buy_count) / data.analyst_count
    return _clamp(ratio * 100.0)


def _extension_pct(data: TickerData) -> float:
    """Return ``current_price / sma_20 − 1``; ``0.0`` if SMA-20 missing."""
    if data.sma_20 <= 0:
        return 0.0
    return data.current_price / data.sma_20 - 1.0


def compute_conviction_score(data: TickerData) -> ScoredTicker:
    """Compute every sub-score, the weighted total, and the over-extension
    penalty for ``data``.

    Args:
        data: TickerData snapshot for a single ticker.

    Returns:
        ScoredTicker with all sub-scores populated, the dampened
        ``conviction_score`` if the ticker is over-extended, and
        ``rank=0``. Call :func:`rank_candidates` to assign final ranks.
    """
    rs_score = _relative_strength_score(data)
    eps_score = _eps_revision_score(data)
    drift_score = _rating_drift_score(data)
    trend_score = _trend_quality_score(data)
    upside_score = _upside_gap_score(data)
    consensus_score = _consensus_strength_score(data)

    raw_total = (
        WEIGHTS["relative_strength"] * rs_score
        + WEIGHTS["eps_revision"] * eps_score
        + WEIGHTS["rating_drift"] * drift_score
        + WEIGHTS["trend_quality"] * trend_score
        + WEIGHTS["upside_gap"] * upside_score
        + WEIGHTS["consensus_strength"] * consensus_score
    )

    extension = _extension_pct(data)
    over_extended = extension > _EXTENSION_PENALTY_THRESHOLD
    total = (
        raw_total * _EXTENSION_PENALTY_FACTOR if over_extended else raw_total
    )

    return ScoredTicker(
        ticker=data.ticker,
        company=data.company,
        conviction_score=round(total, 2),
        relative_strength_score=round(rs_score, 2),
        eps_revision_score=round(eps_score, 2),
        rating_drift_score=round(drift_score, 2),
        trend_quality_score=round(trend_score, 2),
        upside_gap_score=round(upside_score, 2),
        consensus_strength_score=round(consensus_score, 2),
        extension_pct=round(extension, 4),
        over_extended=over_extended,
        rule_of_40=data.rule_of_40,
        earnings_quality=data.earnings_quality,
        rank=0,
    )


def rank_candidates(
    candidates: list[TickerData],
    top_n: int | None = _TOP_N,
) -> list[ScoredTicker]:
    """Score all candidates, sort descending, return the top-ranked subset.

    Args:
        candidates: List of TickerData from ``apply_forward_momentum``.
        top_n: Maximum number of results to return.  Pass ``None`` to
            return all scored candidates without a cap (useful for
            small custom watchlists where every ticker matters).
            Defaults to ``_TOP_N`` (20) to match the weekly report cap.

    Returns:
        Up to ``top_n`` (or all, if ``None``) ScoredTicker instances
        sorted by ``conviction_score`` descending; rank 1 = highest.
    """
    scored = [compute_conviction_score(d) for d in candidates]
    scored.sort(key=lambda x: x.conviction_score, reverse=True)
    subset = scored if top_n is None else scored[:top_n]
    return [s.model_copy(update={"rank": i + 1}) for i, s in enumerate(subset)]
