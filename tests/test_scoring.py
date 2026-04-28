"""Tests for alphavision.scoring (Forward-Momentum Conviction, v3.0)."""

from __future__ import annotations

import pytest

from alphavision.models import ScoredTicker, TickerData
from alphavision.scoring import (
    WEIGHTS,
    _clamp,
    _consensus_strength_score,
    _eps_revision_score,
    _extension_pct,
    _rating_drift_score,
    _relative_strength_score,
    _trend_quality_score,
    _upside_gap_score,
    compute_conviction_score,
    rank_candidates,
)

# ── Test factory ───────────────────────────────────────────────────────────


def _ticker(
    ticker: str = "AAPL",
    company: str = "Apple Inc.",
    current_price: float = 150.0,
    sma_20: float = 145.0,
    sma_200: float = 130.0,
    return_12_1: float = 0.18,
    relative_strength_12_1: float = 0.10,
    target_mean_price: float | None = 180.0,
    analyst_count: int = 20,
    strong_buy_count: int = 8,
    buy_count: int = 6,
    net_upgrades_30d: int = 0,
    eps_revision_slope: float = 0.05,
    rule_of_40: float | None = None,
    earnings_quality: float | None = None,
) -> TickerData:
    return TickerData(
        ticker=ticker,
        company=company,
        current_price=current_price,
        sma_20=sma_20,
        sma_200=sma_200,
        return_12_1=return_12_1,
        relative_strength_12_1=relative_strength_12_1,
        target_mean_price=target_mean_price,
        analyst_count=analyst_count,
        strong_buy_count=strong_buy_count,
        buy_count=buy_count,
        net_upgrades_30d=net_upgrades_30d,
        eps_revision_slope=eps_revision_slope,
        rule_of_40=rule_of_40,
        earnings_quality=earnings_quality,
    )


# ── _clamp ─────────────────────────────────────────────────────────────────


class TestClamp:
    def test_value_within_range_is_unchanged(self) -> None:
        assert _clamp(50.0) == 50.0

    def test_value_below_min_is_clamped_to_zero(self) -> None:
        assert _clamp(-10.0) == 0.0

    def test_value_above_max_is_clamped_to_100(self) -> None:
        assert _clamp(150.0) == 100.0

    def test_exact_boundaries(self) -> None:
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0


# ── _relative_strength_score ──────────────────────────────────────────────


class TestRelativeStrengthScore:
    def test_zero_outperformance_returns_50(self) -> None:
        assert _relative_strength_score(
            _ticker(relative_strength_12_1=0.0)
        ) == pytest.approx(50.0)

    def test_25_pct_outperformance_returns_100(self) -> None:
        # 50 + 0.25 * 200 = 100
        assert _relative_strength_score(
            _ticker(relative_strength_12_1=0.25)
        ) == pytest.approx(100.0)

    def test_negative_25_pct_returns_zero(self) -> None:
        assert _relative_strength_score(
            _ticker(relative_strength_12_1=-0.25)
        ) == pytest.approx(0.0)

    def test_extreme_positive_clamped_to_100(self) -> None:
        assert (
            _relative_strength_score(_ticker(relative_strength_12_1=1.0))
            == 100.0
        )

    def test_extreme_negative_clamped_to_zero(self) -> None:
        assert (
            _relative_strength_score(_ticker(relative_strength_12_1=-1.0))
            == 0.0
        )


# ── _eps_revision_score ────────────────────────────────────────────────────


class TestEpsRevisionScore:
    def test_zero_revision_returns_50(self) -> None:
        assert _eps_revision_score(
            _ticker(eps_revision_slope=0.0)
        ) == pytest.approx(50.0)

    def test_positive_10_pct_revision_returns_100(self) -> None:
        # 50 + 0.10 * 500 = 100
        assert _eps_revision_score(
            _ticker(eps_revision_slope=0.10)
        ) == pytest.approx(100.0)

    def test_negative_10_pct_revision_returns_zero(self) -> None:
        # 50 + (-0.10) * 500 = 0
        assert _eps_revision_score(
            _ticker(eps_revision_slope=-0.10)
        ) == pytest.approx(0.0)

    def test_extreme_positive_clamped(self) -> None:
        t = _ticker(eps_revision_slope=1.0)
        assert _eps_revision_score(t) == 100.0

    def test_extreme_negative_clamped(self) -> None:
        t = _ticker(eps_revision_slope=-1.0)
        assert _eps_revision_score(t) == 0.0


# ── _rating_drift_score ────────────────────────────────────────────────────


class TestRatingDriftScore:
    def test_zero_net_upgrades_returns_50(self) -> None:
        # 50 + 0 * 10 = 50 (neutral)
        assert _rating_drift_score(
            _ticker(net_upgrades_30d=0)
        ) == pytest.approx(50.0)

    def test_5_net_upgrades_returns_100(self) -> None:
        # 50 + 5 * 10 = 100
        assert _rating_drift_score(
            _ticker(net_upgrades_30d=5)
        ) == pytest.approx(100.0)

    def test_minus_5_net_upgrades_returns_zero(self) -> None:
        # 50 + (-5) * 10 = 0
        assert _rating_drift_score(
            _ticker(net_upgrades_30d=-5)
        ) == pytest.approx(0.0)

    def test_extreme_positive_clamped_to_100(self) -> None:
        assert _rating_drift_score(_ticker(net_upgrades_30d=100)) == 100.0

    def test_extreme_negative_clamped_to_zero(self) -> None:
        assert _rating_drift_score(_ticker(net_upgrades_30d=-100)) == 0.0


# ── _trend_quality_score ──────────────────────────────────────────────────


class TestTrendQualityScore:
    def test_price_at_sma_200_returns_50(self) -> None:
        t = _ticker(current_price=130.0, sma_200=130.0)
        assert _trend_quality_score(t) == pytest.approx(50.0)

    def test_price_25_pct_above_sma_returns_100(self) -> None:
        # 50 + 0.25 * 200 = 100
        t = _ticker(current_price=125.0, sma_200=100.0)
        assert _trend_quality_score(t) == pytest.approx(100.0)

    def test_price_25_pct_below_sma_returns_zero(self) -> None:
        t = _ticker(current_price=75.0, sma_200=100.0)
        assert _trend_quality_score(t) == pytest.approx(0.0)

    def test_extreme_positive_clamped_to_100(self) -> None:
        t = _ticker(current_price=200.0, sma_200=100.0)
        assert _trend_quality_score(t) == 100.0

    def test_zero_sma_returns_zero(self) -> None:
        t = _ticker(sma_200=0.0)
        assert _trend_quality_score(t) == 0.0


# ── _upside_gap_score ─────────────────────────────────────────────────────


class TestUpsideGapScore:
    def test_no_target_returns_zero(self) -> None:
        assert _upside_gap_score(_ticker(target_mean_price=None)) == 0.0

    def test_zero_current_price_returns_zero(self) -> None:
        assert _upside_gap_score(_ticker(current_price=0.0)) == 0.0

    def test_30_pct_upside_returns_100(self) -> None:
        # target/current - 1 = 0.30; 0.30 / 0.30 * 100 = 100
        assert _upside_gap_score(
            _ticker(current_price=100.0, target_mean_price=130.0)
        ) == pytest.approx(100.0)

    def test_15_pct_upside_returns_50(self) -> None:
        assert _upside_gap_score(
            _ticker(current_price=100.0, target_mean_price=115.0)
        ) == pytest.approx(50.0)

    def test_negative_upside_returns_zero(self) -> None:
        assert (
            _upside_gap_score(
                _ticker(current_price=100.0, target_mean_price=80.0)
            )
            == 0.0
        )

    def test_above_30_pct_upside_capped_at_100(self) -> None:
        assert (
            _upside_gap_score(
                _ticker(current_price=100.0, target_mean_price=300.0)
            )
            == 100.0
        )


# ── _consensus_strength_score ─────────────────────────────────────────────


class TestConsensusStrengthScore:
    def test_no_analysts_returns_zero(self) -> None:
        assert _consensus_strength_score(_ticker(analyst_count=0)) == 0.0

    def test_all_positive_returns_100(self) -> None:
        t = _ticker(analyst_count=10, strong_buy_count=6, buy_count=4)
        assert _consensus_strength_score(t) == pytest.approx(100.0)

    def test_half_positive_returns_50(self) -> None:
        t = _ticker(analyst_count=10, strong_buy_count=3, buy_count=2)
        assert _consensus_strength_score(t) == pytest.approx(50.0)

    def test_zero_positive_returns_zero(self) -> None:
        t = _ticker(analyst_count=10, strong_buy_count=0, buy_count=0)
        assert _consensus_strength_score(t) == 0.0


# ── _extension_pct ────────────────────────────────────────────────────────


class TestExtensionPct:
    def test_price_at_sma_returns_zero(self) -> None:
        t = _ticker(current_price=145.0, sma_20=145.0)
        assert _extension_pct(t) == pytest.approx(0.0)

    def test_price_above_sma_returns_positive(self) -> None:
        t = _ticker(current_price=160.0, sma_20=145.0)
        assert _extension_pct(t) == pytest.approx(160.0 / 145.0 - 1.0)

    def test_price_below_sma_returns_negative(self) -> None:
        t = _ticker(current_price=140.0, sma_20=145.0)
        assert _extension_pct(t) < 0

    def test_zero_sma_returns_zero(self) -> None:
        t = _ticker(sma_20=0.0)
        assert _extension_pct(t) == 0.0


# ── WEIGHTS ───────────────────────────────────────────────────────────────


class TestWeights:
    def test_weights_sum_to_one(self) -> None:
        assert sum(WEIGHTS.values()) == pytest.approx(1.0)

    def test_relative_strength_is_30_pct(self) -> None:
        assert WEIGHTS["relative_strength"] == pytest.approx(0.30)

    def test_eps_revision_is_25_pct(self) -> None:
        assert WEIGHTS["eps_revision"] == pytest.approx(0.25)

    def test_rating_drift_is_15_pct(self) -> None:
        assert WEIGHTS["rating_drift"] == pytest.approx(0.15)

    def test_trend_quality_is_15_pct(self) -> None:
        assert WEIGHTS["trend_quality"] == pytest.approx(0.15)

    def test_upside_gap_is_10_pct(self) -> None:
        assert WEIGHTS["upside_gap"] == pytest.approx(0.10)

    def test_consensus_strength_is_5_pct(self) -> None:
        assert WEIGHTS["consensus_strength"] == pytest.approx(0.05)

    def test_forward_factors_total_70_pct(self) -> None:
        forward = (
            WEIGHTS["relative_strength"]
            + WEIGHTS["eps_revision"]
            + WEIGHTS["trend_quality"]
        )
        assert forward == pytest.approx(0.70)


# ── compute_conviction_score ──────────────────────────────────────────────


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

    def test_score_in_valid_range(self) -> None:
        score = compute_conviction_score(_ticker()).conviction_score
        assert 0.0 <= score <= 100.0

    def test_score_is_deterministic(self) -> None:
        t = _ticker()
        a = compute_conviction_score(t).conviction_score
        b = compute_conviction_score(t).conviction_score
        assert a == b

    def test_no_analyst_data_does_not_crash(self) -> None:
        t = _ticker(
            target_mean_price=None,
            analyst_count=0,
            strong_buy_count=0,
            buy_count=0,
            net_upgrades_30d=0,
            eps_revision_slope=0.0,
        )
        result = compute_conviction_score(t)
        assert 0.0 <= result.conviction_score <= 100.0

    def test_perfect_score_inputs_yield_100(self) -> None:
        # RS: +25% → 100. EPS slope: +10% → 100. Drift: 5 net upgrades → 100.
        # Trend: +25% above SMA200 → 100. Upside: +30% → 100. Cons: 100% → 100.
        # Extension: price at sma_20 → 0% → no penalty.
        t = _ticker(
            current_price=125.0,
            sma_20=125.0,
            sma_200=100.0,
            return_12_1=0.30,
            relative_strength_12_1=0.25,
            target_mean_price=162.5,  # 30% upside → upside score 100
            analyst_count=10,
            strong_buy_count=10,
            buy_count=0,
            net_upgrades_30d=5,  # 50 + 5*10 = 100
            eps_revision_slope=0.10,  # 50 + 0.10*500 = 100
        )
        result = compute_conviction_score(t)
        assert result.conviction_score == pytest.approx(100.0)
        assert not result.over_extended

    def test_over_extended_dampens_score_by_10_pct(self) -> None:
        # Extension > 10% above sma_20 triggers the 0.90 penalty.
        t = _ticker(
            current_price=125.0,
            sma_20=110.0,  # 125/110 = 13.6% above → over-extended
            sma_200=100.0,
            return_12_1=0.30,
            relative_strength_12_1=0.25,
            target_mean_price=162.5,
            analyst_count=10,
            strong_buy_count=10,
            buy_count=0,
            net_upgrades_30d=5,
            eps_revision_slope=0.10,
        )
        result = compute_conviction_score(t)
        # Raw would be 100; penalty makes it 90
        assert result.conviction_score == pytest.approx(90.0)
        assert result.over_extended

    def test_extension_below_threshold_does_not_dampen(self) -> None:
        # extension = 5% < 10% threshold → no penalty
        t = _ticker(current_price=105.0, sma_20=100.0)
        result = compute_conviction_score(t)
        assert not result.over_extended

    def test_extension_pct_persisted_on_scored_ticker(self) -> None:
        t = _ticker(current_price=160.0, sma_20=145.0)
        result = compute_conviction_score(t)
        assert result.extension_pct == pytest.approx(
            round(160.0 / 145.0 - 1.0, 4)
        )

    def test_rule_of_40_passed_through(self) -> None:
        t = _ticker(rule_of_40=42.5)
        assert compute_conviction_score(t).rule_of_40 == pytest.approx(42.5)

    def test_rule_of_40_none_passed_through(self) -> None:
        t = _ticker(rule_of_40=None)
        assert compute_conviction_score(t).rule_of_40 is None

    def test_earnings_quality_passed_through(self) -> None:
        t = _ticker(earnings_quality=1.75)
        assert compute_conviction_score(t).earnings_quality == pytest.approx(
            1.75
        )

    def test_earnings_quality_none_passed_through(self) -> None:
        t = _ticker(earnings_quality=None)
        assert compute_conviction_score(t).earnings_quality is None

    def test_all_scores_are_rounded_to_two_decimals(self) -> None:
        result = compute_conviction_score(_ticker())
        for score in (
            result.conviction_score,
            result.relative_strength_score,
            result.eps_revision_score,
            result.rating_drift_score,
            result.trend_quality_score,
            result.upside_gap_score,
            result.consensus_strength_score,
        ):
            assert round(score, 2) == score


# ── rank_candidates ───────────────────────────────────────────────────────


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

    def test_top_n_none_returns_all_without_cap(self) -> None:
        tickers = [_ticker(ticker=str(i)) for i in range(25)]
        assert len(rank_candidates(tickers, top_n=None)) == 25

    def test_top_n_explicit_cap(self) -> None:
        tickers = [_ticker(ticker=str(i)) for i in range(10)]
        assert len(rank_candidates(tickers, top_n=3)) == 3

    def test_top_n_larger_than_candidates_returns_all(self) -> None:
        tickers = [_ticker(ticker=str(i)) for i in range(5)]
        assert len(rank_candidates(tickers, top_n=20)) == 5

    def test_sorted_descending_by_score(self) -> None:
        high = _ticker(
            ticker="HIGH",
            relative_strength_12_1=0.30,
            eps_revision_slope=0.10,
            net_upgrades_30d=5,
            strong_buy_count=10,
            analyst_count=10,
            buy_count=0,
        )
        low = _ticker(
            ticker="LOW",
            relative_strength_12_1=-0.20,
            eps_revision_slope=-0.05,
            net_upgrades_30d=-3,
            strong_buy_count=0,
            analyst_count=10,
            buy_count=0,
            target_mean_price=None,
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
