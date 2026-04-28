"""Pydantic models for AlphaVision equity data."""

from __future__ import annotations

from pydantic import BaseModel


class TickerData(BaseModel):
    """Forward-momentum financial snapshot for a single equity ticker.

    Attributes:
        ticker: Stock ticker symbol (e.g. ``"AAPL"``).
        company: Company long name; defaults to ticker if unavailable.
        current_price: Most recent closing price.
        sma_20: 20-day simple moving average.
        sma_200: 200-day simple moving average.
        return_12_1: Jegadeesh-Titman 12-1 month return.
        relative_strength_12_1: ``return_12_1`` minus the SPY benchmark
            ``return_12_1``; populated by ``fetch_universe``.
        target_mean_price: Consensus mean price target; ``None`` if
            unavailable.
        analyst_count: Number of analysts in the latest recommendation
            snapshot.
        strong_buy_count: Strong Buy votes in the latest snapshot.
        buy_count: Buy votes in the latest snapshot.
        net_upgrades_30d: ``upgrades − downgrades`` over the trailing
            30 days; primary signal for the v3.0 Rating Drift score.
        eps_revision_slope: Mean fractional revision of forward-quarter
            EPS estimates vs. their 7d / 30d / 60d / 90d snapshots;
            positive = upward revisions.
        rule_of_40: ``revenue_growth_yoy_% + fcf_margin_%``; ``None``
            if any input is unavailable.
        earnings_quality: ``free_cash_flow / net_income`` for the latest
            reporting period; ``None`` if net income is missing or zero.
    """

    ticker: str
    company: str = ""
    current_price: float
    sma_20: float
    sma_200: float
    return_12_1: float
    relative_strength_12_1: float = 0.0
    target_mean_price: float | None = None
    analyst_count: int = 0
    strong_buy_count: int = 0
    buy_count: int = 0
    net_upgrades_30d: int = 0
    eps_revision_slope: float = 0.0
    rule_of_40: float | None = None
    earnings_quality: float | None = None


class ScoredTicker(BaseModel):
    """Conviction-scored equity with rank and stress-test diagnostics.

    Attributes:
        ticker: Stock ticker symbol.
        company: Company long name.
        conviction_score: Weighted total in ``[0, 100]`` after the
            over-extension penalty has been applied.
        relative_strength_score: 12-1 RS sub-score ``[0, 100]``.
        eps_revision_score: EPS revision-slope sub-score ``[0, 100]``.
        rating_drift_score: Net-upgrades sub-score ``[0, 100]``.
        trend_quality_score: Price-vs-SMA200 sub-score ``[0, 100]``.
        upside_gap_score: Analyst-target sub-score ``[0, 100]``.
        consensus_strength_score: Strong-Buy + Buy fraction sub-score
            ``[0, 100]``.
        extension_pct: ``current_price / sma_20 − 1``.
        over_extended: ``True`` iff the conviction score has been
            dampened by the over-extension penalty.
        rule_of_40: Informational quality signal; ``None`` when data is
            unavailable.
        earnings_quality: Informational FCF/NetIncome ratio; ``None``
            when data is unavailable.
        rank: Weekly rank (1 = highest conviction); 0 before ranking.
    """

    ticker: str
    company: str
    conviction_score: float
    relative_strength_score: float
    eps_revision_score: float
    rating_drift_score: float
    trend_quality_score: float
    upside_gap_score: float
    consensus_strength_score: float
    extension_pct: float
    over_extended: bool
    rule_of_40: float | None
    earnings_quality: float | None
    rank: int
