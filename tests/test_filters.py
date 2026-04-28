"""Tests for alphavision.filters (Forward-Momentum gate, v3.0)."""

from __future__ import annotations

from alphavision.filters import (
    EXTENSION_CAP,
    MIN_ANALYST_COUNT,
    RETURN_12_1_THRESHOLD,
    SMA_200_MULTIPLIER,
    apply_forward_momentum,
    passes_forward_momentum,
)
from alphavision.models import TickerData


def _ticker(
    ticker: str = "TEST",
    current_price: float = 150.0,
    sma_20: float = 145.0,
    sma_200: float = 130.0,
    return_12_1: float = 0.18,
    analyst_count: int = 10,
) -> TickerData:
    """Return a TickerData configured to pass the Forward-Momentum gate."""
    return TickerData(
        ticker=ticker,
        company="Test Corp.",
        current_price=current_price,
        sma_20=sma_20,
        sma_200=sma_200,
        return_12_1=return_12_1,
        target_mean_price=200.0,
        analyst_count=analyst_count,
        strong_buy_count=4,
        buy_count=3,
    )


# ── Constants ─────────────────────────────────────────────────────────────


class TestConstants:
    def test_sma_200_multiplier_is_one(self) -> None:
        assert SMA_200_MULTIPLIER == 1.0

    def test_return_12_1_threshold_is_zero(self) -> None:
        assert RETURN_12_1_THRESHOLD == 0.0

    def test_extension_cap_is_115_pct(self) -> None:
        assert EXTENSION_CAP == 1.15

    def test_min_analyst_count_is_three(self) -> None:
        assert MIN_ANALYST_COUNT == 3


# ── passes_forward_momentum ───────────────────────────────────────────────


class TestPassesForwardMomentum:
    def test_all_gates_pass_returns_true(self) -> None:
        assert passes_forward_momentum(_ticker())

    def test_price_at_or_below_sma_200_returns_false(self) -> None:
        # current_price == sma_200 → fails (strict greater-than gate)
        assert not passes_forward_momentum(
            _ticker(current_price=130.0, sma_200=130.0)
        )

    def test_price_below_sma_200_returns_false(self) -> None:
        assert not passes_forward_momentum(
            _ticker(current_price=120.0, sma_200=130.0)
        )

    def test_negative_12_1_return_returns_false(self) -> None:
        assert not passes_forward_momentum(_ticker(return_12_1=-0.05))

    def test_zero_12_1_return_returns_false(self) -> None:
        assert not passes_forward_momentum(_ticker(return_12_1=0.0))

    def test_over_extended_above_115_pct_sma_20_returns_false(self) -> None:
        # current_price = 1.20 × sma_20 → fails extension gate
        assert not passes_forward_momentum(
            _ticker(current_price=180.0, sma_20=150.0)
        )

    def test_exactly_at_extension_cap_returns_true(self) -> None:
        # current_price = 1.15 × sma_20 → passes (≤ inclusive)
        t = _ticker(current_price=172.5, sma_20=150.0, sma_200=130.0)
        assert passes_forward_momentum(t)

    def test_just_above_extension_cap_returns_false(self) -> None:
        t = _ticker(current_price=172.6, sma_20=150.0, sma_200=130.0)
        assert not passes_forward_momentum(t)

    def test_low_analyst_count_returns_false(self) -> None:
        assert not passes_forward_momentum(_ticker(analyst_count=2))

    def test_at_min_analyst_count_returns_true(self) -> None:
        assert passes_forward_momentum(_ticker(analyst_count=3))

    def test_zero_analyst_count_passes_gate(self) -> None:
        # analyst_count == 0 means "data unavailable" (e.g. no Finnhub key),
        # not "truly uncovered" — let the ticker through rather than block all.
        assert passes_forward_momentum(_ticker(analyst_count=0))

    def test_zero_sma_200_returns_false(self) -> None:
        # Defensive: corrupted data must not produce a pass.
        assert not passes_forward_momentum(_ticker(sma_200=0.0))

    def test_zero_sma_20_returns_false(self) -> None:
        assert not passes_forward_momentum(_ticker(sma_20=0.0))


# ── apply_forward_momentum ────────────────────────────────────────────────


class TestApplyForwardMomentum:
    def test_empty_universe_returns_empty_list(self) -> None:
        assert apply_forward_momentum([]) == []

    def test_passing_ticker_is_included(self) -> None:
        t = _ticker()
        assert t in apply_forward_momentum([t])

    def test_failing_ticker_is_excluded(self) -> None:
        t = _ticker(return_12_1=-0.10)  # fails momentum gate
        assert t not in apply_forward_momentum([t])

    def test_preserves_input_order(self) -> None:
        a = _ticker("A")
        b = _ticker("B")
        result = apply_forward_momentum([a, b])
        assert [r.ticker for r in result] == ["A", "B"]

    def test_mixed_universe_returns_correct_subset(self) -> None:
        ok1 = _ticker("OK1")
        ok2 = _ticker("OK2")
        bad_trend = _ticker("BAD_T", current_price=100.0, sma_200=130.0)
        bad_mom = _ticker("BAD_M", return_12_1=-0.20)
        bad_ext = _ticker("BAD_E", current_price=200.0, sma_20=150.0)
        bad_ana = _ticker("BAD_A", analyst_count=1)

        result = apply_forward_momentum(
            [ok1, bad_trend, ok2, bad_mom, bad_ext, bad_ana]
        )
        tickers = [d.ticker for d in result]
        assert tickers == ["OK1", "OK2"]
