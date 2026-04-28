"""Tests for alphavision.data_fetcher (v3.0 provider architecture)."""

from __future__ import annotations

from unittest.mock import call, patch

import pytest

import alphavision.data_fetcher as df_mod
from alphavision.data_fetcher import (
    _MAX_RETRY_ROUNDS,
    _RATE_LIMIT_COOLDOWN,
    _passes_price_gate,
    fetch_ticker,
    fetch_universe,
    fetch_universe_two_phase,
)
from alphavision.models import TickerData
from alphavision.providers.analyst import AnalystSnapshot
from alphavision.providers.fundamentals import FundamentalsSnapshot
from alphavision.providers.prices import PriceSnapshot

# ── Snapshot / TickerData builders ────────────────────────────────────────


def _price(
    ticker: str = "AAPL",
    company: str = "Apple Inc.",
    current_price: float = 150.0,
    sma_20: float = 145.0,
    sma_200: float = 130.0,
    return_12_1: float = 0.18,
) -> PriceSnapshot:
    return PriceSnapshot(
        ticker=ticker,
        company=company,
        current_price=current_price,
        sma_20=sma_20,
        sma_200=sma_200,
        return_12_1=return_12_1,
    )


def _analyst(
    ticker: str = "AAPL",
    net_upgrades_30d: int = 2,
    eps_revision_slope: float = 0.04,
    target_mean_price: float | None = 180.0,
    analyst_count: int = 20,
    strong_buy_count: int = 8,
    buy_count: int = 6,
) -> AnalystSnapshot:
    return AnalystSnapshot(
        ticker=ticker,
        net_upgrades_30d=net_upgrades_30d,
        eps_revision_slope=eps_revision_slope,
        target_mean_price=target_mean_price,
        analyst_count=analyst_count,
        strong_buy_count=strong_buy_count,
        buy_count=buy_count,
    )


def _fundamentals(
    ticker: str = "AAPL",
    rule_of_40: float | None = 45.0,
    earnings_quality: float | None = 1.3,
) -> FundamentalsSnapshot:
    return FundamentalsSnapshot(
        ticker=ticker,
        rule_of_40=rule_of_40,
        earnings_quality=earnings_quality,
    )


def _ticker_data(
    ticker: str = "AAPL",
    return_12_1: float = 0.18,
) -> TickerData:
    return TickerData(
        ticker=ticker,
        company="Test Corp.",
        current_price=150.0,
        sma_20=145.0,
        sma_200=130.0,
        return_12_1=return_12_1,
    )


# ── fetch_ticker — happy path ─────────────────────────────────────────────


class TestFetchTickerHappyPath:
    def test_returns_ticker_data_instance(self) -> None:
        with (
            patch.object(
                df_mod, "fetch_price_snapshot", return_value=_price()
            ),
            patch.object(
                df_mod, "fetch_analyst_snapshot", return_value=_analyst()
            ),
            patch.object(
                df_mod,
                "fetch_fundamentals_snapshot",
                return_value=_fundamentals(),
            ),
        ):
            result = fetch_ticker("AAPL")
        assert isinstance(result, TickerData)

    def test_ticker_field_matches_input(self) -> None:
        with (
            patch.object(
                df_mod,
                "fetch_price_snapshot",
                return_value=_price("MSFT", "Microsoft"),
            ),
            patch.object(
                df_mod,
                "fetch_analyst_snapshot",
                return_value=_analyst("MSFT"),
            ),
            patch.object(
                df_mod,
                "fetch_fundamentals_snapshot",
                return_value=_fundamentals("MSFT"),
            ),
        ):
            result = fetch_ticker("MSFT")
        assert result.ticker == "MSFT"

    def test_price_fields_propagate(self) -> None:
        p = _price(
            current_price=200.0,
            sma_20=195.0,
            sma_200=180.0,
            return_12_1=0.22,
        )
        with (
            patch.object(df_mod, "fetch_price_snapshot", return_value=p),
            patch.object(
                df_mod, "fetch_analyst_snapshot", return_value=_analyst()
            ),
            patch.object(
                df_mod,
                "fetch_fundamentals_snapshot",
                return_value=_fundamentals(),
            ),
        ):
            result = fetch_ticker("AAPL")
        assert result.current_price == pytest.approx(200.0)
        assert result.sma_20 == pytest.approx(195.0)
        assert result.sma_200 == pytest.approx(180.0)
        assert result.return_12_1 == pytest.approx(0.22)

    def test_analyst_fields_propagate(self) -> None:
        a = _analyst(
            net_upgrades_30d=3,
            eps_revision_slope=0.06,
            target_mean_price=220.0,
            analyst_count=15,
            strong_buy_count=10,
            buy_count=5,
        )
        with (
            patch.object(
                df_mod, "fetch_price_snapshot", return_value=_price()
            ),
            patch.object(df_mod, "fetch_analyst_snapshot", return_value=a),
            patch.object(
                df_mod,
                "fetch_fundamentals_snapshot",
                return_value=_fundamentals(),
            ),
        ):
            result = fetch_ticker("AAPL")
        assert result.net_upgrades_30d == 3
        assert result.eps_revision_slope == pytest.approx(0.06)
        assert result.target_mean_price == pytest.approx(220.0)
        assert result.analyst_count == 15
        assert result.strong_buy_count == 10
        assert result.buy_count == 5

    def test_fundamentals_fields_propagate(self) -> None:
        f = _fundamentals(rule_of_40=55.0, earnings_quality=1.8)
        with (
            patch.object(
                df_mod, "fetch_price_snapshot", return_value=_price()
            ),
            patch.object(
                df_mod, "fetch_analyst_snapshot", return_value=_analyst()
            ),
            patch.object(
                df_mod, "fetch_fundamentals_snapshot", return_value=f
            ),
        ):
            result = fetch_ticker("AAPL")
        assert result.rule_of_40 == pytest.approx(55.0)
        assert result.earnings_quality == pytest.approx(1.8)

    def test_relative_strength_defaults_to_zero(self) -> None:
        # fetch_ticker does not compute RS — fetch_universe does.
        with (
            patch.object(
                df_mod, "fetch_price_snapshot", return_value=_price()
            ),
            patch.object(
                df_mod, "fetch_analyst_snapshot", return_value=_analyst()
            ),
            patch.object(
                df_mod,
                "fetch_fundamentals_snapshot",
                return_value=_fundamentals(),
            ),
        ):
            result = fetch_ticker("AAPL")
        assert result.relative_strength_12_1 == 0.0

    def test_company_from_price_snapshot(self) -> None:
        p = _price(company="Acme Corp.")
        with (
            patch.object(df_mod, "fetch_price_snapshot", return_value=p),
            patch.object(
                df_mod, "fetch_analyst_snapshot", return_value=_analyst()
            ),
            patch.object(
                df_mod,
                "fetch_fundamentals_snapshot",
                return_value=_fundamentals(),
            ),
        ):
            result = fetch_ticker("AAPL")
        assert result.company == "Acme Corp."


# ── fetch_ticker — provider failures ──────────────────────────────────────


class TestFetchTickerProviderFailures:
    def test_analyst_failure_yields_neutral_defaults(self) -> None:
        with (
            patch.object(
                df_mod, "fetch_price_snapshot", return_value=_price()
            ),
            patch.object(
                df_mod,
                "fetch_analyst_snapshot",
                side_effect=RuntimeError("timeout"),
            ),
            patch.object(
                df_mod,
                "fetch_fundamentals_snapshot",
                return_value=_fundamentals(),
            ),
        ):
            result = fetch_ticker("AAPL")
        assert result.net_upgrades_30d == 0
        assert result.eps_revision_slope == pytest.approx(0.0)
        assert result.analyst_count == 0
        assert result.target_mean_price is None

    def test_fundamentals_failure_yields_none_metrics(self) -> None:
        with (
            patch.object(
                df_mod, "fetch_price_snapshot", return_value=_price()
            ),
            patch.object(
                df_mod, "fetch_analyst_snapshot", return_value=_analyst()
            ),
            patch.object(
                df_mod,
                "fetch_fundamentals_snapshot",
                side_effect=RuntimeError("edgar down"),
            ),
        ):
            result = fetch_ticker("AAPL")
        assert result.rule_of_40 is None
        assert result.earnings_quality is None

    def test_price_failure_propagates(self) -> None:
        with (
            patch.object(
                df_mod,
                "fetch_price_snapshot",
                side_effect=ValueError("Insufficient price history"),
            ),
            patch.object(
                df_mod, "fetch_analyst_snapshot", return_value=_analyst()
            ),
            patch.object(
                df_mod,
                "fetch_fundamentals_snapshot",
                return_value=_fundamentals(),
            ),
        ):
            with pytest.raises(ValueError, match="Insufficient price history"):
                fetch_ticker("AAPL")

    def test_both_secondary_providers_fail(self) -> None:
        with (
            patch.object(
                df_mod, "fetch_price_snapshot", return_value=_price()
            ),
            patch.object(
                df_mod,
                "fetch_analyst_snapshot",
                side_effect=RuntimeError("x"),
            ),
            patch.object(
                df_mod,
                "fetch_fundamentals_snapshot",
                side_effect=RuntimeError("x"),
            ),
        ):
            result = fetch_ticker("AAPL")
        assert isinstance(result, TickerData)
        assert result.net_upgrades_30d == 0
        assert result.rule_of_40 is None


# ── fetch_universe ─────────────────────────────────────────────────────────


class TestFetchUniverse:
    def test_empty_input_returns_empty(self) -> None:
        assert fetch_universe([]) == []

    def test_all_succeed_returns_all(self) -> None:
        def _side(ticker: str) -> TickerData:
            return _ticker_data(ticker)

        with (
            patch.object(df_mod, "fetch_ticker", side_effect=_side),
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.0
            ),
        ):
            result = fetch_universe(["AAPL", "MSFT"])
        assert [r.ticker for r in result] == ["AAPL", "MSFT"]

    def test_failed_ticker_dropped(self) -> None:
        def _side(ticker: str) -> TickerData:
            if ticker == "FAIL":
                raise ValueError("no history")
            return _ticker_data(ticker)

        with (
            patch.object(df_mod, "fetch_ticker", side_effect=_side),
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.0
            ),
        ):
            result = fetch_universe(["AAPL", "FAIL", "MSFT"])
        assert [r.ticker for r in result] == ["AAPL", "MSFT"]

    def test_all_fail_returns_empty(self) -> None:
        with (
            patch.object(df_mod, "fetch_ticker", side_effect=ValueError("x")),
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.0
            ),
        ):
            result = fetch_universe(["A", "B"])
        assert result == []

    def test_input_order_preserved(self) -> None:
        symbols = ["AAPL", "MSFT", "GOOG", "AMZN", "META"]
        with (
            patch.object(
                df_mod,
                "fetch_ticker",
                side_effect=lambda t: _ticker_data(t),
            ),
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.0
            ),
        ):
            result = fetch_universe(symbols, max_workers=5)
        assert [r.ticker for r in result] == symbols

    def test_relative_strength_uses_benchmark_delta(self) -> None:
        td = _ticker_data("AAPL", return_12_1=0.18)
        with (
            patch.object(df_mod, "fetch_ticker", return_value=td),
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.06
            ),
        ):
            result = fetch_universe(["AAPL"])
        assert result[0].relative_strength_12_1 == pytest.approx(0.18 - 0.06)

    def test_max_workers_accepted(self) -> None:
        with (
            patch.object(
                df_mod,
                "fetch_ticker",
                side_effect=lambda t: _ticker_data(t),
            ),
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.0
            ),
        ):
            result = fetch_universe(["AAPL"], max_workers=1)
        assert len(result) == 1


# ── fetch_universe — batch retry ──────────────────────────────────────────


class TestFetchUniverseBatchRetry:
    def test_rate_limited_retried_in_next_round(self) -> None:
        rate_err = ValueError("Too Many Requests.")
        call_count: dict[str, int] = {"SLOW": 0}

        def _side(ticker: str) -> TickerData:
            if ticker == "SLOW":
                call_count["SLOW"] += 1
                if call_count["SLOW"] == 1:
                    raise rate_err
            return _ticker_data(ticker)

        with (
            patch.object(df_mod, "fetch_ticker", side_effect=_side),
            patch("alphavision.data_fetcher.time.sleep"),
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.0
            ),
        ):
            result = fetch_universe(["AAPL", "SLOW", "MSFT"])

        assert {r.ticker for r in result} == {"AAPL", "SLOW", "MSFT"}
        assert call_count["SLOW"] == 2

    def test_permanent_error_dropped_without_retry(self) -> None:
        call_count: dict[str, int] = {"BAD": 0}

        def _side(ticker: str) -> TickerData:
            if ticker == "BAD":
                call_count["BAD"] += 1
                raise ValueError("Insufficient price history")
            return _ticker_data(ticker)

        with (
            patch.object(df_mod, "fetch_ticker", side_effect=_side),
            patch("alphavision.data_fetcher.time.sleep"),
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.0
            ),
        ):
            result = fetch_universe(["AAPL", "BAD", "MSFT"])

        assert all(r.ticker != "BAD" for r in result)
        assert call_count["BAD"] == 1

    def test_cooldown_grows_per_round(self) -> None:
        rate_err = ValueError("Too Many Requests.")
        fail_rounds: list[int] = [0]

        def _side(ticker: str) -> TickerData:
            if ticker == "SLOW" and fail_rounds[0] < 2:
                fail_rounds[0] += 1
                raise rate_err
            return _ticker_data(ticker)

        with (
            patch.object(df_mod, "fetch_ticker", side_effect=_side),
            patch("alphavision.data_fetcher.time.sleep") as mock_sleep,
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.0
            ),
        ):
            fetch_universe(["AAPL", "SLOW"])

        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0] == call(_RATE_LIMIT_COOLDOWN * 1)
        assert mock_sleep.call_args_list[1] == call(_RATE_LIMIT_COOLDOWN * 2)

    def test_all_rate_limited_succeed_on_retry(self) -> None:
        rate_err = ValueError("Too Many Requests.")
        first_call: set[str] = set()

        def _side(ticker: str) -> TickerData:
            if ticker not in first_call:
                first_call.add(ticker)
                raise rate_err
            return _ticker_data(ticker)

        with (
            patch.object(df_mod, "fetch_ticker", side_effect=_side),
            patch("alphavision.data_fetcher.time.sleep"),
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.0
            ),
        ):
            result = fetch_universe(["A", "B", "C"])

        assert len(result) == 3

    def test_exhausted_rounds_omits_still_limited(self) -> None:
        # A ticker that always rate-limits should be omitted after all rounds.
        with (
            patch.object(
                df_mod,
                "fetch_ticker",
                side_effect=ValueError("Too Many Requests."),
            ),
            patch("alphavision.data_fetcher.time.sleep"),
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.0
            ),
            patch.object(df_mod, "_MAX_RETRY_ROUNDS", 2),
        ):
            result = fetch_universe(["STUCK"])

        assert result == []

    def test_constants_reasonable(self) -> None:
        assert _RATE_LIMIT_COOLDOWN > 0
        assert _MAX_RETRY_ROUNDS > 1


# ── probe_providers ───────────────────────────────────────────────────────


class TestProbeProviders:
    def test_no_keys_uses_yfinance_analyst(self) -> None:
        from alphavision.data_fetcher import probe_providers

        with patch.dict(
            "os.environ",
            {"FINNHUB_API_KEY": "", "EDGAR_IDENTITY": ""},
            clear=False,
        ):
            status = probe_providers()
        assert status.analyst_source == "yfinance"
        assert not status.finnhub_key_set
        assert not status.edgar_identity_custom
        assert len(status.warnings) == 2

    def test_with_finnhub_key_uses_finnhub(self) -> None:
        from alphavision.data_fetcher import probe_providers

        with patch.dict(
            "os.environ",
            {"FINNHUB_API_KEY": "test-key", "EDGAR_IDENTITY": ""},
            clear=False,
        ):
            status = probe_providers()
        assert status.analyst_source == "finnhub"
        assert status.finnhub_key_set
        assert not status.edgar_identity_custom

    def test_with_edgar_identity_no_warning(self) -> None:
        from alphavision.data_fetcher import probe_providers

        with patch.dict(
            "os.environ",
            {
                "FINNHUB_API_KEY": "key",
                "EDGAR_IDENTITY": "Test User test@example.com",
            },
            clear=False,
        ):
            status = probe_providers()
        assert status.edgar_identity_custom
        assert status.warnings == []

    def test_prices_always_yfinance(self) -> None:
        from alphavision.data_fetcher import probe_providers

        with patch.dict("os.environ", {}, clear=False):
            status = probe_providers()
        assert status.prices_source == "yfinance"

    def test_fundamentals_always_edgar(self) -> None:
        from alphavision.data_fetcher import probe_providers

        with patch.dict("os.environ", {}, clear=False):
            status = probe_providers()
        assert status.fundamentals_source == "edgar"


# ── _passes_price_gate ────────────────────────────────────────────────────


class TestPassesPriceGate:
    def test_passes_when_all_conditions_met(self) -> None:
        snap = _price(
            current_price=150.0,
            sma_200=130.0,
            sma_20=145.0,
            return_12_1=0.10,
        )
        assert _passes_price_gate(snap)

    def test_fails_when_price_below_sma200(self) -> None:
        snap = _price(
            current_price=120.0,
            sma_200=130.0,
            sma_20=118.0,
            return_12_1=0.10,
        )
        assert not _passes_price_gate(snap)

    def test_fails_when_negative_12_1_return(self) -> None:
        snap = _price(
            current_price=150.0,
            sma_200=130.0,
            sma_20=145.0,
            return_12_1=-0.05,
        )
        assert not _passes_price_gate(snap)

    def test_fails_when_over_extended(self) -> None:
        snap = _price(
            current_price=170.0,
            sma_200=130.0,
            sma_20=140.0,  # 170/140 = 1.214 > 1.15
            return_12_1=0.10,
        )
        assert not _passes_price_gate(snap)

    def test_fails_when_sma200_is_zero(self) -> None:
        snap = _price(sma_200=0.0, sma_20=145.0)
        assert not _passes_price_gate(snap)

    def test_fails_when_sma20_is_zero(self) -> None:
        snap = _price(sma_200=130.0, sma_20=0.0)
        assert not _passes_price_gate(snap)


# ── fetch_universe_two_phase ──────────────────────────────────────────────


class TestFetchUniverseTwoPhase:
    def _patch_two_phase(
        self,
        price_batch: dict[str, PriceSnapshot],
        ticker_data: TickerData,
        benchmark: float = 0.05,
    ) -> tuple[object, object, object]:
        return (
            patch.object(
                df_mod, "fetch_price_batch", return_value=price_batch
            ),
            patch.object(
                df_mod,
                "_fetch_analyst_and_fundamentals",
                return_value=ticker_data,
            ),
            patch.object(
                df_mod,
                "fetch_benchmark_return_12_1",
                return_value=benchmark,
            ),
        )

    def test_empty_tickers_returns_empty(self) -> None:
        result, scanned = fetch_universe_two_phase([])
        assert result == []
        assert scanned == 0

    def test_returns_scanned_count(self) -> None:
        snap = _price(
            current_price=150.0, sma_200=130.0, sma_20=145.0, return_12_1=0.10
        )
        td = _ticker_data()
        p1, p2, p3 = self._patch_two_phase({"AAPL": snap}, td)
        with p1, p2, p3:
            result, scanned = fetch_universe_two_phase(
                ["AAPL", "MSFT", "NVDA"]
            )
        assert scanned == 3

    def test_price_gate_filters_tickers(self) -> None:
        passing_snap = _price(
            current_price=150.0, sma_200=130.0, sma_20=145.0, return_12_1=0.10
        )
        failing_snap = _price(
            current_price=100.0, sma_200=130.0, sma_20=98.0, return_12_1=0.05
        )
        td = _ticker_data()
        p1, p2, p3 = self._patch_two_phase(
            {"AAPL": passing_snap, "MSFT": failing_snap}, td
        )
        with p1, p2, p3:
            result, _ = fetch_universe_two_phase(["AAPL", "MSFT"])
        # Only AAPL passed the price gate
        assert len(result) == 1
        assert result[0].ticker == "AAPL"

    def test_no_survivors_returns_empty(self) -> None:
        failing = _price(
            current_price=100.0, sma_200=130.0, sma_20=98.0, return_12_1=-0.05
        )
        with patch.object(
            df_mod, "fetch_price_batch", return_value={"AAPL": failing}
        ):
            result, scanned = fetch_universe_two_phase(["AAPL"])
        assert result == []
        assert scanned == 1

    def test_benchmark_subtracted_from_return(self) -> None:
        snap = _price(
            current_price=150.0, sma_200=130.0, sma_20=145.0, return_12_1=0.18
        )
        td = _ticker_data()
        p1, p2, p3 = self._patch_two_phase({"AAPL": snap}, td, benchmark=0.10)
        with p1, p2, p3:
            result, _ = fetch_universe_two_phase(["AAPL"])
        assert result[0].relative_strength_12_1 == pytest.approx(
            td.return_12_1 - 0.10
        )

    def test_company_lookup_forwarded_to_batch(self) -> None:
        snap = _price()
        td = _ticker_data()
        p1, p2, p3 = self._patch_two_phase({"AAPL": snap}, td)
        lookup = {"AAPL": "Apple Inc."}
        with p1 as mock_batch, p2, p3:
            fetch_universe_two_phase(["AAPL"], company_lookup=lookup)
        mock_batch.assert_called_once_with(["AAPL"], company_lookup=lookup)

    def test_status_fn_called_with_progress(self) -> None:
        snap = _price()
        td = _ticker_data()
        messages: list[str] = []
        p1, p2, p3 = self._patch_two_phase({"AAPL": snap}, td)
        with p1, p2, p3:
            fetch_universe_two_phase(["AAPL"], status_fn=messages.append)
        assert len(messages) > 0

    def test_phase2_future_exception_skips_ticker(self) -> None:
        snap = _price(
            current_price=150.0, sma_200=130.0, sma_20=145.0, return_12_1=0.10
        )
        with (
            patch.object(
                df_mod, "fetch_price_batch", return_value={"AAPL": snap}
            ),
            patch.object(
                df_mod,
                "_fetch_analyst_and_fundamentals",
                side_effect=RuntimeError("boom"),
            ),
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.0
            ),
        ):
            result, scanned = fetch_universe_two_phase(["AAPL"])
        assert result == []
        assert scanned == 1


# ── _fetch_analyst_and_fundamentals ──────────────────────────────────────


class TestFetchAnalystAndFundamentals:
    def test_analyst_failure_falls_back_to_defaults(self) -> None:
        from alphavision.data_fetcher import _fetch_analyst_and_fundamentals

        p = _price()
        with (
            patch.object(
                df_mod,
                "fetch_analyst_snapshot",
                side_effect=ValueError("no data"),
            ),
            patch.object(
                df_mod,
                "fetch_fundamentals_snapshot",
                return_value=_fundamentals(),
            ),
        ):
            td = _fetch_analyst_and_fundamentals("AAPL", p)
        assert td.analyst_count == 0
        assert td.net_upgrades_30d == 0

    def test_fundamentals_failure_falls_back_to_defaults(self) -> None:
        from alphavision.data_fetcher import _fetch_analyst_and_fundamentals

        p = _price()
        with (
            patch.object(
                df_mod, "fetch_analyst_snapshot", return_value=_analyst()
            ),
            patch.object(
                df_mod,
                "fetch_fundamentals_snapshot",
                side_effect=ValueError("no data"),
            ),
        ):
            td = _fetch_analyst_and_fundamentals("AAPL", p)
        assert td.rule_of_40 is None
        assert td.earnings_quality is None

    def test_price_fields_propagate(self) -> None:
        from alphavision.data_fetcher import _fetch_analyst_and_fundamentals

        p = _price(
            ticker="MSFT",
            company="Microsoft",
            current_price=300.0,
            sma_20=290.0,
            sma_200=250.0,
            return_12_1=0.25,
        )
        with (
            patch.object(
                df_mod, "fetch_analyst_snapshot", return_value=_analyst()
            ),
            patch.object(
                df_mod,
                "fetch_fundamentals_snapshot",
                return_value=_fundamentals(),
            ),
        ):
            td = _fetch_analyst_and_fundamentals("MSFT", p)
        assert td.current_price == pytest.approx(300.0)
        assert td.company == "Microsoft"
        assert td.return_12_1 == pytest.approx(0.25)


# ── fetch_universe status_fn branches ────────────────────────────────────


class TestFetchUniverseStatusFn:
    def test_status_fn_called_on_success(self) -> None:
        messages: list[str] = []
        with (
            patch.object(
                df_mod,
                "fetch_ticker",
                side_effect=lambda t: _ticker_data(t),
            ),
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.0
            ),
        ):
            fetch_universe(["AAPL"], status_fn=messages.append)
        assert any("AAPL" in m or "fetch" in m.lower() for m in messages)

    def test_status_fn_called_on_exhausted_retries(self) -> None:
        messages: list[str] = []
        with (
            patch.object(
                df_mod,
                "fetch_ticker",
                side_effect=ValueError("Too Many Requests."),
            ),
            patch("alphavision.data_fetcher.time.sleep"),
            patch.object(
                df_mod, "fetch_benchmark_return_12_1", return_value=0.0
            ),
            patch.object(df_mod, "_MAX_RETRY_ROUNDS", 2),
        ):
            fetch_universe(["STUCK"], status_fn=messages.append)
        assert any("Warning" in m or "omitted" in m for m in messages)
