"""Conviction Score engine for AlphaVision equity ranking."""

from __future__ import annotations

import logging

from alphavision.filters import passes_momentum, passes_turnaround
from alphavision.models import ScoredTicker, TickerData

# Alternatives considered:
# - ML-based ranking: requires labeled historical weekly Top 20 (back-test
#   data not yet available); deferred to a later phase.
# - Equal weighting: ignores the primacy of analyst upside gap; METADOLOGY.md
#   assigns 40% to upside gap based on empirical evidence of predictive value.
# - Dynamic weights per sector: adds complexity without MVP-phase benefit.
# Fixed METADOLOGY.md weights provide transparency and reproducibility.

logger = logging.getLogger(__name__)

WEIGHTS: dict[str, float] = {
    "upside_gap": 0.40,
    "rating_drift": 0.30,
    "consensus_strength": 0.20,
    "eps_momentum": 0.10,
}

_TOP_N: int = 20

# Normalization constants — documented for auditability
_UPSIDE_CAP: float = 0.50  # 50% analyst upside → sub-score 100
_EPS_SCALE: float = 500.0  # ±10% EPS revision → sub-score swing of ±50 pts


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, value))


def _upside_gap_score(data: TickerData) -> float:
    """Analyst target upside normalized to [0, 100].

    0% upside → 0; 50% upside → 100 (capped).
    """
    if data.target_mean_price is None or data.current_price <= 0:
        return 0.0
    upside = (data.target_mean_price / data.current_price) - 1.0
    return _clamp(upside / _UPSIDE_CAP * 100.0)


def _rating_drift_score(data: TickerData) -> float:
    """Strong Buy analyst fraction as rating-upgrade-momentum proxy, [0, 100].

    Measures extreme positive conviction: fraction of analysts with the
    highest possible rating (Strong Buy).
    """
    if data.analyst_count <= 0:
        return 0.0
    return _clamp(data.strong_buy_count / data.analyst_count * 100.0)


def _consensus_strength_score(data: TickerData) -> float:
    """Fraction of Strong Buy + Buy ratings among all analysts, [0, 100]."""
    if data.analyst_count <= 0:
        return 0.0
    ratio = (data.strong_buy_count + data.buy_count) / data.analyst_count
    return _clamp(ratio * 100.0)


def _eps_momentum_score(data: TickerData) -> float:
    """EPS revision direction scaled to [0, 100], centered at 50.

    0.0 revision → 50; +10% → 100; -10% → 0.
    """
    return _clamp(50.0 + data.eps_revision_direction * _EPS_SCALE)


def _determine_channel(data: TickerData) -> str:
    """Return 'A', 'B', or 'BOTH' based on Dual-Track gate results."""
    t = passes_turnaround(data)
    m = passes_momentum(data)
    if t and m:
        return "BOTH"
    if t:
        return "A"
    return "B"


def compute_conviction_score(data: TickerData) -> ScoredTicker:
    """Compute all four sub-scores and the weighted Conviction Score.

    Each sub-score is in [0, 100]. The weighted total is also in [0, 100].
    Rank is set to 0; call rank_candidates() to assign final ranks.

    Args:
        data: TickerData snapshot for a single ticker.

    Returns:
        ScoredTicker with all score components and channel assignment.
    """
    upside_score = _upside_gap_score(data)
    drift_score = _rating_drift_score(data)
    consensus_score = _consensus_strength_score(data)
    eps_score = _eps_momentum_score(data)

    total = (
        WEIGHTS["upside_gap"] * upside_score
        + WEIGHTS["rating_drift"] * drift_score
        + WEIGHTS["consensus_strength"] * consensus_score
        + WEIGHTS["eps_momentum"] * eps_score
    )

    return ScoredTicker(
        ticker=data.ticker,
        company=data.company,
        conviction_score=round(total, 2),
        upside_gap_score=round(upside_score, 2),
        rating_drift_score=round(drift_score, 2),
        consensus_strength_score=round(consensus_score, 2),
        eps_momentum_score=round(eps_score, 2),
        rank=0,
        channel=_determine_channel(data),
    )


def rank_candidates(candidates: list[TickerData]) -> list[ScoredTicker]:
    """Score all candidates, sort descending, return top _TOP_N with ranks.

    Args:
        candidates: List of TickerData from apply_dual_track().

    Returns:
        Up to _TOP_N ScoredTicker instances sorted by conviction_score
        descending; rank 1 = highest scoring.
    """
    scored = [compute_conviction_score(d) for d in candidates]
    scored.sort(key=lambda x: x.conviction_score, reverse=True)
    return [
        s.model_copy(update={"rank": i + 1})
        for i, s in enumerate(scored[:_TOP_N])
    ]
