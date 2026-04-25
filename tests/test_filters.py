"""Tests for alphavision.filters."""

from __future__ import annotations

from alphavision.filters import (
    MOMENTUM_RETURN_THRESHOLD,
    MOMENTUM_SMA_MULTIPLIER,
    TURNAROUND_DRAWDOWN_THRESHOLD,
    apply_dual_track,
    passes_momentum,
    passes_turnaround,
)
from alphavision.models import TickerData

# ── Shared fixtures ────────────────────────────────────────────────────────


def _ticker(
    ticker: str = "TEST",
    drawdown_pct: float = -0.10,
    current_price: float = 150.0,
    sma_200: float = 140.0,
    return_6m: float = 0.10,
) -> TickerData:
    """Return a TickerData with only filter-relevant fields configured."""
    return TickerData(
        ticker=ticker,
        company="Test Corp.",
        current_price=current_price,
        price_6m_high=current_price / (1.0 + drawdown_pct),
        drawdown_pct=drawdown_pct,
        sma_200=sma_200,
        return_6m=return_6m,
        target_mean_price=200.0,
        analyst_count=20,
        strong_buy_count=8,
        buy_count=6,
        eps_revision_direction=0.05,
    )


# ── Constants ─────────────────────────────────────────────────────────────


class TestConstants:
    def test_turnaround_threshold_is_minus_25_pct(self) -> None:
        assert TURNAROUND_DRAWDOWN_THRESHOLD == -0.25

    def test_momentum_sma_multiplier_is_one(self) -> None:
        assert MOMENTUM_SMA_MULTIPLIER == 1.0

    def test_momentum_return_threshold_is_zero(self) -> None:
        assert MOMENTUM_RETURN_THRESHOLD == 0.0


# ── passes_turnaround ──────────────────────────────────────────────────────


class TestPassesTurnaround:
    def test_drawdown_below_threshold_returns_true(self) -> None:
        assert passes_turnaround(_ticker(drawdown_pct=-0.30))

    def test_drawdown_exactly_at_threshold_returns_true(self) -> None:
        assert passes_turnaround(_ticker(drawdown_pct=-0.25))

    def test_drawdown_above_threshold_returns_false(self) -> None:
        assert not passes_turnaround(_ticker(drawdown_pct=-0.20))

    def test_no_drawdown_returns_false(self) -> None:
        assert not passes_turnaround(_ticker(drawdown_pct=0.0))

    def test_positive_price_action_returns_false(self) -> None:
        assert not passes_turnaround(_ticker(drawdown_pct=0.05))

    def test_extreme_drawdown_returns_true(self) -> None:
        assert passes_turnaround(_ticker(drawdown_pct=-0.60))


# ── passes_momentum ────────────────────────────────────────────────────────


class TestPassesMomentum:
    def test_price_above_sma_and_positive_return_returns_true(self) -> None:
        assert passes_momentum(
            _ticker(current_price=150.0, sma_200=140.0, return_6m=0.10)
        )

    def test_price_below_sma_returns_false(self) -> None:
        assert not passes_momentum(
            _ticker(current_price=130.0, sma_200=140.0, return_6m=0.10)
        )

    def test_price_equal_to_sma_returns_false(self) -> None:
        assert not passes_momentum(
            _ticker(current_price=140.0, sma_200=140.0, return_6m=0.10)
        )

    def test_negative_return_returns_false(self) -> None:
        assert not passes_momentum(
            _ticker(current_price=150.0, sma_200=140.0, return_6m=-0.05)
        )

    def test_zero_return_returns_false(self) -> None:
        assert not passes_momentum(
            _ticker(current_price=150.0, sma_200=140.0, return_6m=0.0)
        )

    def test_price_above_sma_but_negative_return_returns_false(self) -> None:
        assert not passes_momentum(
            _ticker(current_price=150.0, sma_200=100.0, return_6m=-0.10)
        )


# ── apply_dual_track ───────────────────────────────────────────────────────


class TestApplyDualTrack:
    def test_empty_universe_returns_empty_list(self) -> None:
        assert apply_dual_track([]) == []

    def test_channel_a_only_ticker_is_included(self) -> None:
        # Drawdown -30% (passes A), price < SMA (fails B)
        t = _ticker(drawdown_pct=-0.30, current_price=100.0, sma_200=120.0)
        assert t in apply_dual_track([t])

    def test_channel_b_only_ticker_is_included(self) -> None:
        # No drawdown (fails A), price > SMA and positive return (passes B)
        t = _ticker(drawdown_pct=-0.10, current_price=150.0, sma_200=140.0)
        assert t in apply_dual_track([t])

    def test_ticker_passing_both_appears_once(self) -> None:
        # Passes both A and B
        t = _ticker(
            drawdown_pct=-0.30,
            current_price=150.0,
            sma_200=140.0,
            return_6m=0.05,
        )
        result = apply_dual_track([t])
        assert result.count(t) == 1

    def test_ticker_failing_both_is_excluded(self) -> None:
        # Fails A (drawdown -10%) and fails B (price < SMA)
        t = _ticker(drawdown_pct=-0.10, current_price=100.0, sma_200=120.0)
        assert t not in apply_dual_track([t])

    def test_preserves_input_order(self) -> None:
        a = _ticker("A", drawdown_pct=-0.30)
        b = _ticker("B", current_price=150.0, sma_200=140.0, return_6m=0.10)
        result = apply_dual_track([a, b])
        assert result[0].ticker == "A"
        assert result[1].ticker == "B"

    def test_mixed_universe_returns_correct_subset(self) -> None:
        pass_a = _ticker("PA", drawdown_pct=-0.30)
        pass_b = _ticker(
            "PB", drawdown_pct=-0.10, current_price=150.0, sma_200=140.0
        )
        fail = _ticker(
            "F", drawdown_pct=-0.10, current_price=100.0, sma_200=120.0
        )
        result = apply_dual_track([pass_a, pass_b, fail])
        tickers = [d.ticker for d in result]
        assert "PA" in tickers
        assert "PB" in tickers
        assert "F" not in tickers
        assert len(result) == 2
