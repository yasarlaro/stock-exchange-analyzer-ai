"""Tests for alphavision.data_fetcher."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from alphavision.data_fetcher import (
    _extract_analyst_counts,
    _extract_eps_revision,
    _is_rate_limited,
    fetch_ticker,
    fetch_universe,
)
from alphavision.models import TickerData

# ── Shared test data ──────────────────────────────────────────────────────


def _make_price_history(
    n_rows: int = 252, base: float = 100.0
) -> pd.DataFrame:
    """Create a monotonically increasing price history DataFrame."""
    dates = pd.date_range(end="2026-04-24", periods=n_rows, freq="B")
    closes = [base + i * 0.1 for i in range(n_rows)]
    return pd.DataFrame({"Close": closes}, index=dates)


def _make_recommendations(
    strong_buy: int = 10,
    buy: int = 8,
) -> pd.DataFrame:
    """Create a synthetic recommendations_summary DataFrame."""
    return pd.DataFrame(
        {
            "period": ["0m", "-1m", "-2m"],
            "strongBuy": [strong_buy, 9, 8],
            "buy": [buy, 7, 6],
            "hold": [5, 5, 5],
            "sell": [1, 1, 1],
            "strongSell": [0, 0, 0],
        }
    )


def _make_eps_trend(
    current: float = 5.0,
    ago_30: float = 4.5,
) -> pd.DataFrame:
    """Create a synthetic EPS trend DataFrame."""
    return pd.DataFrame(
        {
            "current": [current, current * 1.1],
            "7daysAgo": [current * 0.99, current * 1.09],
            "30daysAgo": [ago_30, ago_30 * 1.1],
            "60daysAgo": [ago_30 * 0.95, ago_30 * 1.05],
            "90daysAgo": [ago_30 * 0.90, ago_30 * 1.0],
        },
        index=["0q", "+1q"],
    )


def _make_ticker_data(ticker: str = "AAPL") -> TickerData:
    """Return a minimal valid TickerData instance."""
    return TickerData(
        ticker=ticker,
        current_price=150.0,
        price_6m_high=160.0,
        drawdown_pct=-0.0625,
        sma_200=140.0,
        return_6m=0.10,
        target_mean_price=210.0,
        analyst_count=30,
        strong_buy_count=10,
        buy_count=8,
        eps_revision_direction=0.11,
    )


@pytest.fixture
def mock_ticker_cls() -> Generator[MagicMock]:
    """Patch yf.Ticker and configure a default mock Ticker instance."""
    with patch("alphavision.data_fetcher.yf.Ticker") as mock_cls:
        t = MagicMock()
        t.info = {
            "currentPrice": 150.0,
            "targetMeanPrice": 210.0,
            "numberOfAnalystOpinions": 30,
        }
        t.history.return_value = _make_price_history()
        t.recommendations_summary = _make_recommendations()
        t.get_eps_trend.return_value = _make_eps_trend()
        mock_cls.return_value = t
        yield mock_cls


# ── _extract_analyst_counts ────────────────────────────────────────────────


class TestExtractAnalystCounts:
    def test_non_dataframe_returns_zeros(self) -> None:
        assert _extract_analyst_counts(None) == (0, 0)
        assert _extract_analyst_counts("string") == (0, 0)
        assert _extract_analyst_counts(42) == (0, 0)

    def test_empty_dataframe_returns_zeros(self) -> None:
        assert _extract_analyst_counts(pd.DataFrame()) == (0, 0)

    def test_no_period_column_returns_zeros(self) -> None:
        df = pd.DataFrame({"strongBuy": [10], "buy": [8]})
        assert _extract_analyst_counts(df) == (0, 0)

    def test_no_current_period_row_returns_zeros(self) -> None:
        df = pd.DataFrame(
            {"period": ["-1m", "-2m"], "strongBuy": [9, 8], "buy": [7, 6]}
        )
        assert _extract_analyst_counts(df) == (0, 0)

    def test_valid_data_returns_correct_counts(self) -> None:
        df = _make_recommendations(strong_buy=12, buy=9)
        assert _extract_analyst_counts(df) == (12, 9)

    def test_missing_strong_buy_column_returns_zero_for_it(self) -> None:
        df = pd.DataFrame({"period": ["0m"], "buy": [8]})
        assert _extract_analyst_counts(df) == (0, 8)

    def test_missing_buy_column_returns_zero_for_it(self) -> None:
        df = pd.DataFrame({"period": ["0m"], "strongBuy": [10]})
        assert _extract_analyst_counts(df) == (10, 0)


# ── _extract_eps_revision ──────────────────────────────────────────────────


class TestExtractEpsRevision:
    def test_non_dataframe_returns_zero(self) -> None:
        assert _extract_eps_revision(None) == 0.0
        assert _extract_eps_revision("x") == 0.0

    def test_empty_dataframe_returns_zero(self) -> None:
        assert _extract_eps_revision(pd.DataFrame()) == 0.0

    def test_missing_current_column_returns_zero(self) -> None:
        df = pd.DataFrame({"30daysAgo": [4.5]})
        assert _extract_eps_revision(df) == 0.0

    def test_missing_30days_ago_column_returns_zero(self) -> None:
        df = pd.DataFrame({"current": [5.0]})
        assert _extract_eps_revision(df) == 0.0

    def test_upward_revision_returns_positive(self) -> None:
        df = _make_eps_trend(current=5.0, ago_30=4.5)
        result = _extract_eps_revision(df)
        assert result == pytest.approx((5.0 - 4.5) / 4.5)

    def test_downward_revision_returns_negative(self) -> None:
        df = _make_eps_trend(current=4.0, ago_30=4.5)
        assert _extract_eps_revision(df) < 0

    def test_zero_ago_30_returns_zero(self) -> None:
        df = _make_eps_trend(current=5.0, ago_30=0.0)
        assert _extract_eps_revision(df) == 0.0

    def test_non_numeric_values_return_zero(self) -> None:
        df = pd.DataFrame(
            {"current": ["n/a"], "30daysAgo": ["n/a"]}, index=["0q"]
        )
        assert _extract_eps_revision(df) == 0.0


# ── fetch_ticker happy path ────────────────────────────────────────────────


class TestFetchTickerHappyPath:
    def test_returns_ticker_data_instance(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        assert isinstance(fetch_ticker("AAPL"), TickerData)

    def test_ticker_field_matches_input(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        assert fetch_ticker("MSFT").ticker == "MSFT"

    def test_current_price_is_last_close(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        hist = _make_price_history()
        expected = float(hist["Close"].iloc[-1])
        assert fetch_ticker("AAPL").current_price == pytest.approx(expected)

    def test_price_6m_high_is_max_of_last_126_days(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        hist = _make_price_history()
        expected = float(hist["Close"].iloc[-126:].max())
        assert fetch_ticker("AAPL").price_6m_high == pytest.approx(expected)

    def test_drawdown_pct_is_non_positive_for_monotonic_history(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        assert fetch_ticker("AAPL").drawdown_pct <= 0

    def test_drawdown_pct_calculated_correctly(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        n = 252
        dates = pd.date_range(end="2026-04-24", periods=n, freq="B")
        # Last close = 90.0; 6m window max = 100.0
        closes = [100.0] * (n - 1) + [90.0]
        mock_ticker_cls.return_value.history.return_value = pd.DataFrame(
            {"Close": closes}, index=dates
        )
        result = fetch_ticker("AAPL")
        assert result.drawdown_pct == pytest.approx(-0.10)

    def test_return_6m_calculated_correctly(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        n = 252
        dates = pd.date_range(end="2026-04-24", periods=n, freq="B")
        # 6m start = closes[126] = 110.0; current = 121.0
        closes = [100.0] * 126 + [110.0] * 125 + [121.0]
        mock_ticker_cls.return_value.history.return_value = pd.DataFrame(
            {"Close": closes}, index=dates
        )
        result = fetch_ticker("AAPL")
        assert result.return_6m == pytest.approx(11.0 / 110.0)

    def test_target_mean_price_populated(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        assert fetch_ticker("AAPL").target_mean_price == 210.0

    def test_analyst_count_populated(self, mock_ticker_cls: MagicMock) -> None:
        assert fetch_ticker("AAPL").analyst_count == 30

    def test_strong_buy_count_populated(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        assert fetch_ticker("AAPL").strong_buy_count == 10

    def test_buy_count_populated(self, mock_ticker_cls: MagicMock) -> None:
        assert fetch_ticker("AAPL").buy_count == 8

    def test_eps_revision_positive_for_upward_revision(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        assert fetch_ticker("AAPL").eps_revision_direction > 0


# ── fetch_ticker edge cases ────────────────────────────────────────────────


class TestFetchTickerEdgeCases:
    def test_target_mean_price_none_when_missing_from_info(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        mock_ticker_cls.return_value.info = {"numberOfAnalystOpinions": 5}
        assert fetch_ticker("AAPL").target_mean_price is None

    def test_analyst_count_zero_when_missing_from_info(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        mock_ticker_cls.return_value.info = {"targetMeanPrice": 200.0}
        assert fetch_ticker("AAPL").analyst_count == 0

    def test_short_history_uses_available_data(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        mock_ticker_cls.return_value.history.return_value = (
            _make_price_history(n_rows=50)
        )
        result = fetch_ticker("AAPL")
        assert isinstance(result, TickerData)
        assert result.current_price > 0

    def test_eps_revision_zero_when_trend_unavailable(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        mock_ticker_cls.return_value.get_eps_trend.return_value = None
        assert fetch_ticker("AAPL").eps_revision_direction == 0.0

    def test_analyst_counts_zero_when_recommendations_unavailable(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        mock_ticker_cls.return_value.recommendations_summary = None
        result = fetch_ticker("AAPL")
        assert result.strong_buy_count == 0
        assert result.buy_count == 0

    def test_info_not_dict_yields_none_target_and_zero_count(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        mock_ticker_cls.return_value.info = None
        result = fetch_ticker("AAPL")
        assert result.target_mean_price is None
        assert result.analyst_count == 0


# ── fetch_ticker error cases ───────────────────────────────────────────────


class TestFetchTickerErrors:
    def test_empty_history_raises_value_error(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        mock_ticker_cls.return_value.history.return_value = pd.DataFrame()
        with pytest.raises(ValueError, match="Insufficient price history"):
            fetch_ticker("AAPL")

    def test_single_row_history_raises_value_error(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        mock_ticker_cls.return_value.history.return_value = (
            _make_price_history(n_rows=1)
        )
        with pytest.raises(ValueError, match="Insufficient price history"):
            fetch_ticker("AAPL")

    def test_non_dataframe_history_raises_value_error(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        mock_ticker_cls.return_value.history.return_value = None
        with pytest.raises(ValueError, match="Insufficient price history"):
            fetch_ticker("AAPL")


# ── _is_rate_limited ───────────────────────────────────────────────────────


class TestIsRateLimited:
    def test_too_many_requests_returns_true(self) -> None:
        assert _is_rate_limited(ValueError("Too Many Requests. Rate limited."))

    def test_rate_limited_string_returns_true(self) -> None:
        assert _is_rate_limited(RuntimeError("Rate limited. Try again."))

    def test_generic_error_returns_false(self) -> None:
        assert not _is_rate_limited(ValueError("Insufficient price history"))

    def test_empty_message_returns_false(self) -> None:
        assert not _is_rate_limited(Exception(""))


# ── fetch_universe ─────────────────────────────────────────────────────────


class TestFetchUniverse:
    def test_empty_input_returns_empty_list(self) -> None:
        assert fetch_universe([]) == []

    def test_all_succeed_returns_full_list(self) -> None:
        def _side(ticker: str) -> TickerData:
            return _make_ticker_data(ticker)

        with patch("alphavision.data_fetcher.fetch_ticker", side_effect=_side):
            result = fetch_universe(["AAPL", "MSFT"])
        assert len(result) == 2
        assert result[0].ticker == "AAPL"
        assert result[1].ticker == "MSFT"

    def test_failed_ticker_is_skipped(self) -> None:
        def _side(ticker: str) -> TickerData:
            if ticker == "FAIL":
                raise ValueError("test error")
            return _make_ticker_data(ticker)

        with patch("alphavision.data_fetcher.fetch_ticker", side_effect=_side):
            result = fetch_universe(["AAPL", "FAIL", "MSFT"])
        assert len(result) == 2
        assert all(r.ticker != "FAIL" for r in result)

    def test_all_fail_returns_empty_list(self) -> None:
        with patch(
            "alphavision.data_fetcher.fetch_ticker",
            side_effect=ValueError("no data"),
        ):
            result = fetch_universe(["A", "B", "C"])
        assert result == []

    def test_max_workers_parameter_is_accepted(self) -> None:
        with patch(
            "alphavision.data_fetcher.fetch_ticker",
            side_effect=lambda t: _make_ticker_data(t),
        ):
            result = fetch_universe(["AAPL"], max_workers=1)
        assert len(result) == 1
        assert result[0].ticker == "AAPL"

    def test_input_order_preserved_with_parallel_fetch(self) -> None:
        symbols = ["AAPL", "MSFT", "GOOG", "AMZN", "META"]

        with patch(
            "alphavision.data_fetcher.fetch_ticker",
            side_effect=lambda t: _make_ticker_data(t),
        ):
            result = fetch_universe(symbols, max_workers=5)

        assert [r.ticker for r in result] == symbols

    def test_preserves_order_when_some_fail(self) -> None:
        def _side(ticker: str) -> TickerData:
            if ticker in {"FAIL1", "FAIL2"}:
                raise ValueError("no data")
            return _make_ticker_data(ticker)

        with patch("alphavision.data_fetcher.fetch_ticker", side_effect=_side):
            result = fetch_universe(["AAPL", "FAIL1", "MSFT", "FAIL2", "GOOG"])

        assert len(result) == 3
        assert [r.ticker for r in result] == ["AAPL", "MSFT", "GOOG"]


# ── fetch_universe — batch retry behaviour ────────────────────────────────


class TestFetchUniverseBatchRetry:
    def test_rate_limited_ticker_retried_in_next_round(self) -> None:
        """A rate-limited ticker is not dropped — it appears in the results
        after the retry round succeeds."""
        rate_err = ValueError("Too Many Requests. Rate limited.")
        call_count: dict[str, int] = {"SLOW": 0}

        def _side(ticker: str) -> TickerData:
            if ticker == "SLOW":
                call_count["SLOW"] += 1
                if call_count["SLOW"] == 1:
                    raise rate_err
            return _make_ticker_data(ticker)

        with (
            patch("alphavision.data_fetcher.fetch_ticker", side_effect=_side),
            patch("alphavision.data_fetcher.time.sleep"),
        ):
            result = fetch_universe(["AAPL", "SLOW", "MSFT"])

        assert len(result) == 3
        assert {r.ticker for r in result} == {"AAPL", "SLOW", "MSFT"}
        assert call_count["SLOW"] == 2  # fetched once (fail) + once (success)

    def test_permanent_error_drops_ticker_without_retry(self) -> None:
        """Non-rate-limit error drops the ticker immediately; no retry."""
        call_count: dict[str, int] = {"BAD": 0}

        def _side(ticker: str) -> TickerData:
            if ticker == "BAD":
                call_count["BAD"] += 1
                raise ValueError("Insufficient price history")
            return _make_ticker_data(ticker)

        with (
            patch("alphavision.data_fetcher.fetch_ticker", side_effect=_side),
            patch("alphavision.data_fetcher.time.sleep"),
        ):
            result = fetch_universe(["AAPL", "BAD", "MSFT"])

        assert len(result) == 2
        assert all(r.ticker != "BAD" for r in result)
        assert call_count["BAD"] == 1  # tried exactly once, not retried

    def test_cooldown_sleep_called_between_retry_rounds(self) -> None:
        """time.sleep fires once per failing round with a growing delay."""
        rate_err = ValueError("Too Many Requests. Rate limited.")
        fail_rounds: list[int] = [0]

        def _side(ticker: str) -> TickerData:
            if ticker == "SLOW" and fail_rounds[0] < 2:
                fail_rounds[0] += 1
                raise rate_err
            return _make_ticker_data(ticker)

        from alphavision.data_fetcher import _RATE_LIMIT_COOLDOWN

        with (
            patch("alphavision.data_fetcher.fetch_ticker", side_effect=_side),
            patch("alphavision.data_fetcher.time.sleep") as mock_sleep,
        ):
            fetch_universe(["AAPL", "SLOW"])

        # SLOW fails round 1 and round 2 → two sleeps, growing cooldown
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0] == call(_RATE_LIMIT_COOLDOWN * 1)
        assert mock_sleep.call_args_list[1] == call(_RATE_LIMIT_COOLDOWN * 2)

    def test_all_rate_limited_eventually_returns_all(self) -> None:
        """All tickers rate-limited on round 1 → all succeed on round 2."""
        rate_err = ValueError("Too Many Requests. Rate limited.")
        first_call: set[str] = set()

        def _side(ticker: str) -> TickerData:
            if ticker not in first_call:
                first_call.add(ticker)
                raise rate_err
            return _make_ticker_data(ticker)

        with (
            patch("alphavision.data_fetcher.fetch_ticker", side_effect=_side),
            patch("alphavision.data_fetcher.time.sleep"),
        ):
            result = fetch_universe(["A", "B", "C"])

        assert len(result) == 3
