"""Tests for alphavision.providers.prices."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from alphavision.providers.prices import (
    PriceSnapshot,
    _extract_closes_from_batch,
    compute_return_12_1,
    fetch_benchmark_return_12_1,
    fetch_price_batch,
    fetch_price_snapshot,
    is_rate_limited,
)


def _make_history(n_rows: int = 252, base: float = 100.0) -> pd.DataFrame:
    dates = pd.date_range(end="2026-04-24", periods=n_rows, freq="B")
    closes = [base + i * 0.1 for i in range(n_rows)]
    return pd.DataFrame({"Close": closes}, index=dates)


@pytest.fixture
def mock_yf() -> Generator[MagicMock]:
    with patch("alphavision.providers.prices.yf.Ticker") as mock_cls:
        t = MagicMock()
        t.info = {"longName": "Apple Inc.", "currentPrice": 150.0}
        t.history.return_value = _make_history()
        mock_cls.return_value = t
        yield mock_cls


# ── compute_return_12_1 ───────────────────────────────────────────────────


class TestComputeReturn12Minus1:
    def test_full_history(self) -> None:
        n = 252
        closes = pd.Series([100.0] * (n - 21) + [120.0] * 21)
        assert compute_return_12_1(closes) == pytest.approx(0.20)

    def test_negative_return(self) -> None:
        n = 252
        closes = pd.Series([200.0] * (n - 21) + [150.0] * 21)
        assert compute_return_12_1(closes) == pytest.approx(-0.25)

    def test_short_history_falls_back(self) -> None:
        closes = pd.Series([100.0 + i for i in range(50)])
        # lookback_12 = 50, lookback_1 = 21 → price_1m_ago = closes[29] = 129
        assert compute_return_12_1(closes) == pytest.approx(0.29)

    def test_two_row_history(self) -> None:
        closes = pd.Series([100.0, 110.0])
        assert compute_return_12_1(closes) == pytest.approx(0.10)

    def test_single_row(self) -> None:
        assert compute_return_12_1(pd.Series([100.0])) == 0.0

    def test_empty(self) -> None:
        assert compute_return_12_1(pd.Series(dtype=float)) == 0.0

    def test_zero_anchor(self) -> None:
        n = 252
        closes = pd.Series([0.0] + [100.0] * (n - 1))
        assert compute_return_12_1(closes) == 0.0


# ── fetch_price_snapshot ──────────────────────────────────────────────────


class TestFetchPriceSnapshot:
    def test_returns_snapshot(self, mock_yf: MagicMock) -> None:
        result = fetch_price_snapshot("AAPL")
        assert isinstance(result, PriceSnapshot)
        assert result.ticker == "AAPL"

    def test_company_uses_long_name(self, mock_yf: MagicMock) -> None:
        assert fetch_price_snapshot("AAPL").company == "Apple Inc."

    def test_company_falls_back_to_ticker(self, mock_yf: MagicMock) -> None:
        mock_yf.return_value.info = {}
        assert fetch_price_snapshot("MSFT").company == "MSFT"

    def test_company_when_info_raises(self, mock_yf: MagicMock) -> None:
        type(mock_yf.return_value).info = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("404"))
        )
        assert fetch_price_snapshot("FOO").company == "FOO"

    def test_current_price_is_last_close(self, mock_yf: MagicMock) -> None:
        hist = _make_history()
        expected = float(hist["Close"].iloc[-1])
        assert fetch_price_snapshot("AAPL").current_price == pytest.approx(
            expected
        )

    def test_sma_20_is_last_20_day_mean(self, mock_yf: MagicMock) -> None:
        hist = _make_history()
        expected = float(hist["Close"].iloc[-20:].mean())
        assert fetch_price_snapshot("AAPL").sma_20 == pytest.approx(expected)

    def test_sma_200_is_last_200_day_mean(self, mock_yf: MagicMock) -> None:
        hist = _make_history()
        expected = float(hist["Close"].iloc[-200:].mean())
        assert fetch_price_snapshot("AAPL").sma_200 == pytest.approx(expected)

    def test_return_12_1_positive_for_uptrend(
        self, mock_yf: MagicMock
    ) -> None:
        assert fetch_price_snapshot("AAPL").return_12_1 > 0

    def test_short_history_still_works(self, mock_yf: MagicMock) -> None:
        mock_yf.return_value.history.return_value = _make_history(n_rows=50)
        result = fetch_price_snapshot("AAPL")
        assert result.current_price > 0

    def test_empty_history_raises(self, mock_yf: MagicMock) -> None:
        mock_yf.return_value.history.return_value = pd.DataFrame()
        with pytest.raises(ValueError, match="Insufficient price history"):
            fetch_price_snapshot("AAPL")

    def test_single_row_raises(self, mock_yf: MagicMock) -> None:
        mock_yf.return_value.history.return_value = _make_history(n_rows=1)
        with pytest.raises(ValueError, match="Insufficient price history"):
            fetch_price_snapshot("AAPL")

    def test_non_dataframe_raises(self, mock_yf: MagicMock) -> None:
        mock_yf.return_value.history.return_value = None
        with pytest.raises(ValueError, match="Insufficient price history"):
            fetch_price_snapshot("AAPL")


# ── fetch_benchmark_return_12_1 ──────────────────────────────────────────


class TestFetchBenchmarkReturn12Minus1:
    def test_happy_path(self) -> None:
        hist = _make_history()
        mock_t = MagicMock()
        mock_t.history.return_value = hist
        with patch(
            "alphavision.providers.prices.yf.Ticker", return_value=mock_t
        ):
            result = fetch_benchmark_return_12_1("SPY")
        assert result == pytest.approx(compute_return_12_1(hist["Close"]))

    def test_history_error_returns_zero(self) -> None:
        mock_t = MagicMock()
        mock_t.history.side_effect = ValueError("no data")
        with patch(
            "alphavision.providers.prices.yf.Ticker", return_value=mock_t
        ):
            assert fetch_benchmark_return_12_1("SPY") == 0.0

    def test_empty_history_returns_zero(self) -> None:
        mock_t = MagicMock()
        mock_t.history.return_value = pd.DataFrame()
        with patch(
            "alphavision.providers.prices.yf.Ticker", return_value=mock_t
        ):
            assert fetch_benchmark_return_12_1("SPY") == 0.0

    def test_does_not_use_info_endpoint(self) -> None:
        mock_t = MagicMock()
        mock_t.history.return_value = _make_history()
        type(mock_t).info = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("404"))
        )
        with patch(
            "alphavision.providers.prices.yf.Ticker", return_value=mock_t
        ):
            assert fetch_benchmark_return_12_1("SPY") > 0


# ── _extract_closes_from_batch ────────────────────────────────────────────


class TestExtractClosesFromBatch:
    def _multi_df(self) -> pd.DataFrame:
        dates = pd.date_range("2025-01-01", periods=5, freq="B")
        data = {
            ("AAPL", "Close"): [100.0, 101.0, 102.0, 103.0, 104.0],
            ("AAPL", "Open"): [99.0] * 5,
            ("MSFT", "Close"): [200.0, 201.0, 202.0, 203.0, 204.0],
            ("MSFT", "Open"): [199.0] * 5,
        }
        return pd.DataFrame(data, index=dates)

    def test_multi_index_extracts_correct_ticker(self) -> None:
        df = self._multi_df()
        closes = _extract_closes_from_batch(df, "AAPL", is_multi=True)
        assert len(closes) == 5
        assert float(closes.iloc[-1]) == pytest.approx(104.0)

    def test_multi_index_missing_ticker_returns_empty(self) -> None:
        df = self._multi_df()
        closes = _extract_closes_from_batch(df, "NVDA", is_multi=True)
        assert closes.empty

    def test_flat_index_returns_close_column(self) -> None:
        dates = pd.date_range("2025-01-01", periods=3, freq="B")
        df = pd.DataFrame(
            {"Close": [50.0, 51.0, 52.0], "Open": [49.0] * 3},
            index=dates,
        )
        closes = _extract_closes_from_batch(df, "AAPL", is_multi=False)
        assert len(closes) == 3

    def test_flat_index_no_close_column_returns_empty(self) -> None:
        df = pd.DataFrame({"Open": [10.0, 11.0]})
        closes = _extract_closes_from_batch(df, "AAPL", is_multi=False)
        assert closes.empty

    def test_nan_rows_dropped(self) -> None:
        dates = pd.date_range("2025-01-01", periods=4, freq="B")
        df = pd.DataFrame(
            {("AAPL", "Close"): [100.0, float("nan"), 102.0, 103.0]},
            index=dates,
        )
        closes = _extract_closes_from_batch(df, "AAPL", is_multi=True)
        assert not closes.isna().any()
        assert len(closes) == 3


# ── fetch_price_batch ─────────────────────────────────────────────────────


class TestFetchPriceBatch:
    def _make_multi_df(self, tickers: list[str], n: int = 252) -> pd.DataFrame:
        dates = pd.date_range(end="2026-04-24", periods=n, freq="B")
        data: dict[tuple[str, str], list[float]] = {}
        for i, t in enumerate(tickers):
            base = 100.0 + i * 50
            data[(t, "Close")] = [base + j * 0.1 for j in range(n)]
            data[(t, "Open")] = [base] * n
        return pd.DataFrame(data, index=dates)

    def test_returns_snapshot_for_each_ticker(self) -> None:
        tickers = ["AAPL", "MSFT"]
        mock_df = self._make_multi_df(tickers)
        with patch(
            "alphavision.providers.prices.yf.download",
            return_value=mock_df,
        ):
            result = fetch_price_batch(tickers)
        assert set(result.keys()) == {"AAPL", "MSFT"}
        assert isinstance(result["AAPL"], PriceSnapshot)

    def test_company_lookup_used_when_provided(self) -> None:
        tickers = ["AAPL"]
        mock_df = self._make_multi_df(tickers)
        lookup = {"AAPL": "Apple Inc."}
        with patch(
            "alphavision.providers.prices.yf.download",
            return_value=mock_df,
        ):
            result = fetch_price_batch(tickers, company_lookup=lookup)
        assert result["AAPL"].company == "Apple Inc."

    def test_ticker_falls_back_to_symbol_when_no_lookup(self) -> None:
        tickers = ["AAPL"]
        mock_df = self._make_multi_df(tickers)
        with patch(
            "alphavision.providers.prices.yf.download",
            return_value=mock_df,
        ):
            result = fetch_price_batch(tickers)
        assert result["AAPL"].company == "AAPL"

    def test_empty_tickers_returns_empty_dict(self) -> None:
        result = fetch_price_batch([])
        assert result == {}

    def test_download_failure_returns_empty_dict(self) -> None:
        with patch(
            "alphavision.providers.prices.yf.download",
            side_effect=RuntimeError("network error"),
        ):
            result = fetch_price_batch(["AAPL"])
        assert result == {}

    def test_download_returns_empty_df_returns_empty_dict(self) -> None:
        with patch(
            "alphavision.providers.prices.yf.download",
            return_value=pd.DataFrame(),
        ):
            result = fetch_price_batch(["AAPL"])
        assert result == {}

    def test_ticker_with_insufficient_rows_omitted(self) -> None:
        tickers = ["AAPL", "MSFT"]
        # MSFT needs more rows; test that single-row AAPL is omitted
        mock_df = self._make_multi_df(["MSFT"])
        # Merge to simulate AAPL having only 1 row
        aapl_col = pd.DataFrame(
            {("AAPL", "Close"): [float("nan")] * 251 + [150.0]},
            index=mock_df.index,
        )
        combined = pd.concat([mock_df, aapl_col], axis=1)
        # Drop most AAPL rows
        combined[("AAPL", "Close")] = float("nan")
        combined.loc[combined.index[-1], ("AAPL", "Close")] = 150.0
        with patch(
            "alphavision.providers.prices.yf.download",
            return_value=combined,
        ):
            result = fetch_price_batch(tickers)
        # AAPL should be omitted (< 2 non-NaN rows)
        assert "AAPL" not in result
        assert "MSFT" in result

    def test_sma_values_computed_correctly(self) -> None:
        tickers = ["AAPL"]
        n = 252
        mock_df = self._make_multi_df(tickers, n=n)
        with patch(
            "alphavision.providers.prices.yf.download",
            return_value=mock_df,
        ):
            result = fetch_price_batch(tickers)
        snap = result["AAPL"]
        closes = mock_df["AAPL"]["Close"].dropna()
        expected_sma_20 = float(closes.iloc[-20:].mean())
        assert snap.sma_20 == pytest.approx(expected_sma_20, rel=1e-5)


# ── is_rate_limited ───────────────────────────────────────────────────────


class TestIsRateLimited:
    def test_too_many_requests(self) -> None:
        assert is_rate_limited(ValueError("Too Many Requests."))

    def test_rate_limited_message(self) -> None:
        assert is_rate_limited(RuntimeError("Rate limited."))

    def test_other(self) -> None:
        assert not is_rate_limited(ValueError("history error"))

    def test_empty(self) -> None:
        assert not is_rate_limited(Exception(""))
