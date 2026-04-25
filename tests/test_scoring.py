"""Tests for alphavision.scoring."""

from __future__ import annotations

import pytest

from alphavision.models import ScoredTicker, TickerData
from alphavision.scoring import (
    WEIGHTS,
    _clamp,
    _consensus_strength_score,
    _eps_momentum_score,
    _rating_drift_score,
    _upside_gap_score,
    compute_conviction_score,
    rank_candidates,
)

# ── Test factory ───────────────────────────────────────────────────────────


def _ticker(
    ticker: str = "AAPL",
    company: str = "Apple Inc.",
    current_price: float = 100.0,
    price_6m_high: float = 110.0,
    drawdown_pct: float = -0.30,  # passes Channel A
    sma_200: float = 90.0,  # current > sma_200 for Channel B
    return_6m: float = 0.10,  # positive for Channel B
    target_mean_price: float | None = 150.0,
    analyst_count: int = 20,
    strong_buy_count: int = 10,
    buy_count: int = 6,
    eps_revision_direction: float = 0.05,
) -> TickerData:
    return TickerData(
        ticker=ticker,
        company=company,
        current_price=current_price,
        price_6m_high=price_6m_high,
        drawdown_pct=drawdown_pct,
        sma_200=sma_200,
        return_6m=return_6m,
        target_mean_price=target_mean_price,
        analyst_count=analyst_count,
        strong_buy_count=strong_buy_count,
        buy_count=buy_count,
        eps_revision_direction=eps_revision_direction,
    )


# ── _clamp ─────────────────────────────────────────────────────────────────


class TestClamp:
    def test_value_within_range_is_unchanged(self) -> None:
        assert _clamp(50.0) == 50.0

    def test_value_below_min_is_clamped_to_zero(self) -> None:
        assert _clamp(-10.0) == 0.0

    def test_value_above_max_is_clamped_to_100(self) -> None:
        assert _clamp(150.0) == 100.0

    def test_exact_min_boundary(self) -> None:
        assert _clamp(0.0) == 0.0

    def test_exact_max_boundary(self) -> None:
        assert _clamp(100.0) == 100.0


# ── _upside_gap_score ──────────────────────────────────────────────────────


class TestUpsideGapScore:
    def test_no_target_returns_zero(self) -> None:
        assert _upside_gap_score(_ticker(target_mean_price=None)) == 0.0

    def test_zero_current_price_returns_zero(self) -> None:
        assert _upside_gap_score(_ticker(current_price=0.0)) == 0.0

    def test_50_pct_upside_returns_100(self) -> None:
        # target = 150, current = 100 → upside = 50% → score = 100
        assert _upside_gap_score(
            _ticker(current_price=100.0, target_mean_price=150.0)
        ) == pytest.approx(100.0)

    def test_25_pct_upside_returns_50(self) -> None:
        assert _upside_gap_score(
            _ticker(current_price=100.0, target_mean_price=125.0)
        ) == pytest.approx(50.0)

    def test_negative_upside_returns_zero(self) -> None:
        assert (
            _upside_gap_score(
                _ticker(current_price=100.0, target_mean_price=80.0)
            )
            == 0.0
        )

    def test_over_50_pct_upside_capped_at_100(self) -> None:
        assert (
            _upside_gap_score(
                _ticker(current_price=100.0, target_mean_price=300.0)
            )
            == 100.0
        )


# ── _rating_drift_score ────────────────────────────────────────────────────


class TestRatingDriftScore:
    def test_no_analysts_returns_zero(self) -> None:
        assert _rating_drift_score(_ticker(analyst_count=0)) == 0.0

    def test_all_strong_buy_returns_100(self) -> None:
        t = _ticker(analyst_count=10, strong_buy_count=10)
        assert _rating_drift_score(t) == pytest.approx(100.0)

    def test_half_strong_buy_returns_50(self) -> None:
        t = _ticker(analyst_count=10, strong_buy_count=5)
        assert _rating_drift_score(t) == pytest.approx(50.0)

    def test_zero_strong_buy_returns_zero(self) -> None:
        t = _ticker(analyst_count=10, strong_buy_count=0)
        assert _rating_drift_score(t) == 0.0


# ── _consensus_strength_score ──────────────────────────────────────────────


class TestConsensusStrengthScore:
    def test_no_analysts_returns_zero(self) -> None:
        assert _consensus_strength_score(_ticker(analyst_count=0)) == 0.0

    def test_all_positive_ratings_returns_100(self) -> None:
        t = _ticker(analyst_count=10, strong_buy_count=6, buy_count=4)
        assert _consensus_strength_score(t) == pytest.approx(100.0)

    def test_half_positive_returns_50(self) -> None:
        t = _ticker(analyst_count=10, strong_buy_count=3, buy_count=2)
        assert _consensus_strength_score(t) == pytest.approx(50.0)

    def test_zero_positive_ratings_returns_zero(self) -> None:
        t = _ticker(analyst_count=10, strong_buy_count=0, buy_count=0)
        assert _consensus_strength_score(t) == 0.0


# ── _eps_momentum_score ────────────────────────────────────────────────────


class TestEpsMomentumScore:
    def test_zero_revision_returns_50(self) -> None:
        assert _eps_momentum_score(
            _ticker(eps_revision_direction=0.0)
        ) == pytest.approx(50.0)

    def test_positive_10_pct_revision_returns_100(self) -> None:
        # 50 + 0.10 * 500 = 100
        assert _eps_momentum_score(
            _ticker(eps_revision_direction=0.10)
        ) == pytest.approx(100.0)

    def test_negative_10_pct_revision_returns_zero(self) -> None:
        # 50 + (-0.10) * 500 = 0
        assert _eps_momentum_score(
            _ticker(eps_revision_direction=-0.10)
        ) == pytest.approx(0.0)

    def test_extreme_positive_clamped_to_100(self) -> None:
        assert (
            _eps_momentum_score(_ticker(eps_revision_direction=1.0)) == 100.0
        )

    def test_extreme_negative_clamped_to_zero(self) -> None:
        assert _eps_momentum_score(_ticker(eps_revision_direction=-1.0)) == 0.0


# ── WEIGHTS constant ───────────────────────────────────────────────────────


class TestWeights:
    def test_weights_sum_to_one(self) -> None:
        assert sum(WEIGHTS.values()) == pytest.approx(1.0)

    def test_upside_gap_weight_is_40_pct(self) -> None:
        assert WEIGHTS["upside_gap"] == pytest.approx(0.40)

    def test_rating_drift_weight_is_30_pct(self) -> None:
        assert WEIGHTS["rating_drift"] == pytest.approx(0.30)

    def test_consensus_strength_weight_is_20_pct(self) -> None:
        assert WEIGHTS["consensus_strength"] == pytest.approx(0.20)

    def test_eps_momentum_weight_is_10_pct(self) -> None:
        assert WEIGHTS["eps_momentum"] == pytest.approx(0.10)


# ── compute_conviction_score ───────────────────────────────────────────────


class TestComputeConvictionScore:
    def test_returns_scored_ticker_instance(self) -> None:
        assert isinstance(compute_conviction_score(_ticker()), ScoredTicker)

    def test_ticker_field_matches_input(self) -> None:
        result = compute_conviction_score(_ticker(ticker="MSFT"))
        assert result.ticker == "MSFT"

    def test_company_field_matches_input(self) -> None:
        t = _ticker(company="Microsoft Corp.")
        assert compute_conviction_score(t).company == "Microsoft Corp."

    def test_rank_is_zero_before_ranking(self) -> None:
        assert compute_conviction_score(_ticker()).rank == 0

    def test_conviction_score_in_range(self) -> None:
        score = compute_conviction_score(_ticker()).conviction_score
        assert 0.0 <= score <= 100.0

    def test_conviction_score_is_deterministic(self) -> None:
        t = _ticker()
        assert compute_conviction_score(t).conviction_score == (
            compute_conviction_score(t).conviction_score
        )

    def test_no_analyst_data_does_not_crash(self) -> None:
        t = _ticker(
            target_mean_price=None,
            analyst_count=0,
            strong_buy_count=0,
            buy_count=0,
            eps_revision_direction=0.0,
        )
        result = compute_conviction_score(t)
        assert 0.0 <= result.conviction_score <= 100.0

    def test_channel_both_when_passes_both_gates(self) -> None:
        # drawdown -30% → Channel A; price > SMA and positive return → B
        t = _ticker(
            drawdown_pct=-0.30,
            current_price=150.0,
            sma_200=140.0,
            return_6m=0.10,
        )
        assert compute_conviction_score(t).channel == "BOTH"

    def test_channel_a_when_only_turnaround_passes(self) -> None:
        # drawdown -30% → A; price < SMA → fails B
        t = _ticker(
            drawdown_pct=-0.30,
            current_price=100.0,
            sma_200=120.0,
            return_6m=0.10,
        )
        assert compute_conviction_score(t).channel == "A"

    def test_channel_b_when_only_momentum_passes(self) -> None:
        # drawdown -10% → fails A; price > SMA and positive return → B
        t = _ticker(
            drawdown_pct=-0.10,
            current_price=150.0,
            sma_200=140.0,
            return_6m=0.10,
        )
        assert compute_conviction_score(t).channel == "B"

    def test_perfect_score_inputs_yield_100(self) -> None:
        t = _ticker(
            current_price=100.0,
            target_mean_price=150.0,  # 50% upside → upside score 100
            analyst_count=10,
            strong_buy_count=10,  # 100% strong buy → drift 100
            buy_count=0,  # consensus = 100/10 = 100
            eps_revision_direction=0.10,  # +10% → eps score 100
        )
        result = compute_conviction_score(t)
        assert result.conviction_score == pytest.approx(100.0)

    def test_all_scores_are_rounded_to_two_decimals(self) -> None:
        result = compute_conviction_score(_ticker())
        for score in (
            result.conviction_score,
            result.upside_gap_score,
            result.rating_drift_score,
            result.consensus_strength_score,
            result.eps_momentum_score,
        ):
            assert round(score, 2) == score


# ── rank_candidates ────────────────────────────────────────────────────────


class TestRankCandidates:
    def test_empty_input_returns_empty_list(self) -> None:
        assert rank_candidates([]) == []

    def test_single_candidate_gets_rank_1(self) -> None:
        result = rank_candidates([_ticker()])
        assert result[0].rank == 1

    def test_fewer_than_20_returns_all(self) -> None:
        tickers = [_ticker(ticker=str(i)) for i in range(5)]
        assert len(rank_candidates(tickers)) == 5

    def test_more_than_20_returns_top_20(self) -> None:
        tickers = [_ticker(ticker=str(i)) for i in range(30)]
        assert len(rank_candidates(tickers)) == 20

    def test_sorted_descending_by_conviction_score(self) -> None:
        # High upside ticker: 50% upside → higher score
        high = _ticker(
            ticker="HIGH",
            current_price=100.0,
            target_mean_price=150.0,
            analyst_count=10,
            strong_buy_count=10,
            buy_count=0,
            eps_revision_direction=0.10,
        )
        # No analyst data → lower score
        low = _ticker(
            ticker="LOW",
            target_mean_price=None,
            analyst_count=0,
            strong_buy_count=0,
            buy_count=0,
            eps_revision_direction=0.0,
        )
        result = rank_candidates([low, high])
        assert result[0].ticker == "HIGH"
        assert result[1].ticker == "LOW"

    def test_ranks_are_1_indexed_and_sequential(self) -> None:
        tickers = [_ticker(ticker=str(i)) for i in range(5)]
        result = rank_candidates(tickers)
        assert [r.rank for r in result] == [1, 2, 3, 4, 5]

    def test_rank_20_is_assigned_correctly(self) -> None:
        tickers = [_ticker(ticker=str(i)) for i in range(20)]
        result = rank_candidates(tickers)
        assert result[-1].rank == 20
