"""Pydantic models for AlphaVision equity data."""

from __future__ import annotations

from pydantic import BaseModel


class TickerData(BaseModel):
    """Financial snapshot for a single equity ticker.

    Attributes:
        ticker: Stock ticker symbol (e.g., "AAPL").
        company: Company long name; defaults to ticker if unavailable.
        current_price: Most recent closing price.
        price_6m_high: Highest closing price in the last 6 months (~126 days).
        drawdown_pct: (current_price - price_6m_high) / price_6m_high.
        sma_200: Simple moving average of closing price over last 200 days.
        return_6m: 6-month price return (current - 6m_ago) / 6m_ago.
        target_mean_price: Analyst mean target price; None if unavailable.
        analyst_count: Number of analysts covering the ticker.
        strong_buy_count: Number of Strong Buy ratings (current period).
        buy_count: Number of Buy ratings (current period).
        eps_revision_direction: Positive = upward EPS revisions in last
            30 days.
    """

    ticker: str
    company: str = ""
    current_price: float
    price_6m_high: float
    drawdown_pct: float
    sma_200: float
    return_6m: float
    target_mean_price: float | None
    analyst_count: int
    strong_buy_count: int
    buy_count: int
    eps_revision_direction: float


class ScoredTicker(BaseModel):
    """Conviction-scored equity with rank and channel assignment.

    Attributes:
        ticker: Stock ticker symbol.
        company: Company long name.
        conviction_score: Weighted total score in [0.0, 100.0].
        upside_gap_score: Analyst target upside sub-score [0, 100].
        rating_drift_score: Strong-Buy analyst fraction sub-score [0, 100].
        consensus_strength_score: Buy + Strong-Buy fraction sub-score [0, 100].
        eps_momentum_score: EPS revision direction sub-score [0, 100].
        rank: Weekly rank (1 = highest conviction); 0 before ranking.
        channel: Dual-Track entry channel: 'A', 'B', or 'BOTH'.
    """

    ticker: str
    company: str
    conviction_score: float
    upside_gap_score: float
    rating_drift_score: float
    consensus_strength_score: float
    eps_momentum_score: float
    rank: int
    channel: str
