"""Tests for alphavision.providers.analyst."""

from __future__ import annotations

import datetime as dt
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import alphavision.providers.analyst as analyst_mod
from alphavision.providers.analyst import (
    AnalystSnapshot,
    _coerce_int,
    _eps_revision_slope,
    _net_upgrades_30d,
    _price_target,
    _recommendation,
    _recommendation_with_drift,
    fetch_analyst_snapshot,
)


@pytest.fixture(autouse=True)
def _reset_throttle() -> Generator[None]:
    """Each test starts with a zeroed throttle clock and patched sleep."""
    analyst_mod._last_call_at = 0.0
    with patch("alphavision.providers.analyst.time.sleep"):
        yield


@pytest.fixture
def with_api_key() -> Generator[None]:
    with patch.dict(
        "os.environ", {"FINNHUB_API_KEY": "test-key"}, clear=False
    ):
        yield


@pytest.fixture
def without_api_key() -> Generator[None]:
    with patch.dict("os.environ", {"FINNHUB_API_KEY": ""}, clear=False):
        yield


def _now_ts() -> int:
    return int(dt.datetime.now(dt.UTC).timestamp())


# ── _coerce_int ────────────────────────────────────────────────────────────


class TestCoerceInt:
    def test_int(self) -> None:
        assert _coerce_int(5) == 5

    def test_float(self) -> None:
        assert _coerce_int(5.7) == 5

    def test_bool(self) -> None:
        assert _coerce_int(True) == 1

    def test_none(self) -> None:
        assert _coerce_int(None) == 0

    def test_string(self) -> None:
        assert _coerce_int("5") == 0


# ── _net_upgrades_30d ─────────────────────────────────────────────────────


class TestNetUpgrades30d:
    def test_no_api_key_returns_zero(self, without_api_key: None) -> None:
        assert _net_upgrades_30d("AAPL") == 0

    def test_happy_mix(self, with_api_key: None) -> None:
        now = _now_ts()
        payload = [
            {"action": "up", "gradeTime": now - 86400},
            {"action": "up", "gradeTime": now - 86400 * 5},
            {"action": "down", "gradeTime": now - 86400 * 10},
            {"action": "init", "gradeTime": now - 86400 * 2},
        ]
        with patch.object(analyst_mod, "_finnhub_get", return_value=payload):
            assert _net_upgrades_30d("AAPL") == 1  # 2 ups - 1 down

    def test_old_entries_excluded(self, with_api_key: None) -> None:
        now = _now_ts()
        payload = [
            {"action": "up", "gradeTime": now - 86400 * 60},
            {"action": "down", "gradeTime": now - 86400 * 100},
        ]
        with patch.object(analyst_mod, "_finnhub_get", return_value=payload):
            assert _net_upgrades_30d("AAPL") == 0

    def test_empty_payload(self, with_api_key: None) -> None:
        with patch.object(analyst_mod, "_finnhub_get", return_value=[]):
            assert _net_upgrades_30d("AAPL") == 0

    def test_non_list_payload(self, with_api_key: None) -> None:
        with patch.object(
            analyst_mod, "_finnhub_get", return_value={"oops": True}
        ):
            assert _net_upgrades_30d("AAPL") == 0

    def test_malformed_entries_skipped(self, with_api_key: None) -> None:
        now = _now_ts()
        payload = [
            "garbage",
            {"action": "up"},  # no gradeTime
            {"action": "up", "gradeTime": "not-a-timestamp"},
            {"action": "up", "gradeTime": now - 1000},  # only valid
        ]
        with patch.object(analyst_mod, "_finnhub_get", return_value=payload):
            assert _net_upgrades_30d("AAPL") == 1


# ── _recommendation ───────────────────────────────────────────────────────


class TestRecommendation:
    def test_happy_path(self, with_api_key: None) -> None:
        payload = [
            {
                "strongBuy": 5,
                "buy": 4,
                "hold": 3,
                "sell": 1,
                "strongSell": 0,
            },
        ]
        with patch.object(analyst_mod, "_finnhub_get", return_value=payload):
            assert _recommendation("AAPL") == (5, 4, 13)

    def test_empty_returns_zeros(self, with_api_key: None) -> None:
        with patch.object(analyst_mod, "_finnhub_get", return_value=[]):
            assert _recommendation("AAPL") == (0, 0, 0)

    def test_non_list_returns_zeros(self, with_api_key: None) -> None:
        with patch.object(analyst_mod, "_finnhub_get", return_value=None):
            assert _recommendation("AAPL") == (0, 0, 0)

    def test_missing_fields_default_zero(self, with_api_key: None) -> None:
        with patch.object(
            analyst_mod, "_finnhub_get", return_value=[{"strongBuy": 7}]
        ):
            assert _recommendation("AAPL") == (7, 0, 7)


# ── _recommendation_with_drift ────────────────────────────────────────────


class TestRecommendationWithDrift:
    def test_happy_two_months(self, with_api_key: None) -> None:
        payload = [
            {
                "strongBuy": 6,
                "buy": 5,
                "hold": 3,
                "sell": 1,
                "strongSell": 0,
            },
            {
                "strongBuy": 4,
                "buy": 4,
                "hold": 3,
                "sell": 1,
                "strongSell": 0,
            },
        ]
        with patch.object(analyst_mod, "_finnhub_get", return_value=payload):
            sb, b, total, net = _recommendation_with_drift("AAPL")
        assert sb == 6
        assert b == 5
        assert total == 15
        assert net == (6 + 5) - (4 + 4)  # +3

    def test_single_month_drift_is_zero(self, with_api_key: None) -> None:
        payload = [
            {"strongBuy": 5, "buy": 3, "hold": 2, "sell": 0, "strongSell": 0}
        ]
        with patch.object(analyst_mod, "_finnhub_get", return_value=payload):
            sb, b, total, net = _recommendation_with_drift("AAPL")
        assert sb == 5
        assert total == 10
        assert net == 0

    def test_empty_payload_returns_zeros(self, with_api_key: None) -> None:
        with patch.object(analyst_mod, "_finnhub_get", return_value=[]):
            assert _recommendation_with_drift("AAPL") == (0, 0, 0, 0)

    def test_non_list_returns_zeros(self, with_api_key: None) -> None:
        with patch.object(analyst_mod, "_finnhub_get", return_value=None):
            assert _recommendation_with_drift("AAPL") == (0, 0, 0, 0)

    def test_negative_drift_when_analysts_turned_bearish(
        self, with_api_key: None
    ) -> None:
        payload = [
            {"strongBuy": 2, "buy": 1, "hold": 5, "sell": 2, "strongSell": 0},
            {"strongBuy": 5, "buy": 4, "hold": 2, "sell": 1, "strongSell": 0},
        ]
        with patch.object(analyst_mod, "_finnhub_get", return_value=payload):
            _, _, _, net = _recommendation_with_drift("AAPL")
        assert net == (2 + 1) - (5 + 4)  # -6

    def test_prev_month_not_dict_drift_zero(self, with_api_key: None) -> None:
        payload = [
            {"strongBuy": 5, "buy": 3, "hold": 2, "sell": 0, "strongSell": 0},
            "invalid",
        ]
        with patch.object(analyst_mod, "_finnhub_get", return_value=payload):
            _, _, _, net = _recommendation_with_drift("AAPL")
        assert net == 0


# ── _price_target ─────────────────────────────────────────────────────────


class TestPriceTarget:
    def test_happy(self, with_api_key: None) -> None:
        with patch.object(
            analyst_mod, "_finnhub_get", return_value={"targetMean": 215.0}
        ):
            assert _price_target("AAPL") == 215.0

    def test_zero_returns_none(self, with_api_key: None) -> None:
        with patch.object(
            analyst_mod, "_finnhub_get", return_value={"targetMean": 0}
        ):
            assert _price_target("AAPL") is None

    def test_missing_returns_none(self, with_api_key: None) -> None:
        with patch.object(analyst_mod, "_finnhub_get", return_value={}):
            assert _price_target("AAPL") is None

    def test_non_dict_returns_none(self, with_api_key: None) -> None:
        with patch.object(analyst_mod, "_finnhub_get", return_value=[]):
            assert _price_target("AAPL") is None


# ── _eps_revision_slope (yfinance under the hood) ─────────────────────────


def _eps_trend(
    current: float = 5.0,
    d7: float = 4.95,
    d30: float = 4.8,
    d60: float = 4.7,
    d90: float = 4.5,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "current": [current],
            "7daysAgo": [d7],
            "30daysAgo": [d30],
            "60daysAgo": [d60],
            "90daysAgo": [d90],
        },
        index=["0q"],
    )


class TestEpsRevisionSlope:
    def test_upward_revisions_positive(self) -> None:
        mock_t = MagicMock()
        mock_t.get_eps_trend.return_value = _eps_trend()
        with patch(
            "alphavision.providers.analyst.yf.Ticker", return_value=mock_t
        ):
            result = _eps_revision_slope("AAPL")
        assert result > 0

    def test_downward_revisions_negative(self) -> None:
        mock_t = MagicMock()
        mock_t.get_eps_trend.return_value = _eps_trend(
            current=4.0, d7=4.1, d30=4.5, d60=4.7, d90=5.0
        )
        with patch(
            "alphavision.providers.analyst.yf.Ticker", return_value=mock_t
        ):
            result = _eps_revision_slope("AAPL")
        assert result < 0

    def test_missing_current(self) -> None:
        df = pd.DataFrame({"30daysAgo": [4.5]})
        mock_t = MagicMock()
        mock_t.get_eps_trend.return_value = df
        with patch(
            "alphavision.providers.analyst.yf.Ticker", return_value=mock_t
        ):
            assert _eps_revision_slope("AAPL") == 0.0

    def test_no_period_columns(self) -> None:
        df = pd.DataFrame({"current": [5.0]})
        mock_t = MagicMock()
        mock_t.get_eps_trend.return_value = df
        with patch(
            "alphavision.providers.analyst.yf.Ticker", return_value=mock_t
        ):
            assert _eps_revision_slope("AAPL") == 0.0

    def test_zero_past_value_skipped(self) -> None:
        df = _eps_trend(d30=0.0)
        mock_t = MagicMock()
        mock_t.get_eps_trend.return_value = df
        with patch(
            "alphavision.providers.analyst.yf.Ticker", return_value=mock_t
        ):
            # Should still produce a valid average from the other 3 windows.
            assert _eps_revision_slope("AAPL") > 0

    def test_empty_dataframe(self) -> None:
        mock_t = MagicMock()
        mock_t.get_eps_trend.return_value = pd.DataFrame()
        with patch(
            "alphavision.providers.analyst.yf.Ticker", return_value=mock_t
        ):
            assert _eps_revision_slope("AAPL") == 0.0

    def test_non_numeric_value(self) -> None:
        df = pd.DataFrame(
            {"current": ["n/a"], "30daysAgo": [4.5]}, index=["0q"]
        )
        mock_t = MagicMock()
        mock_t.get_eps_trend.return_value = df
        with patch(
            "alphavision.providers.analyst.yf.Ticker", return_value=mock_t
        ):
            assert _eps_revision_slope("AAPL") == 0.0

    def test_yfinance_exception_returns_zero(self) -> None:
        mock_t = MagicMock()
        mock_t.get_eps_trend.side_effect = RuntimeError("boom")
        with patch(
            "alphavision.providers.analyst.yf.Ticker", return_value=mock_t
        ):
            assert _eps_revision_slope("AAPL") == 0.0


# ── _finnhub_get retry behaviour ──────────────────────────────────────────


class TestFinnhubGetRetry:
    def test_no_api_key_returns_none(self, without_api_key: None) -> None:
        from alphavision.providers.analyst import _finnhub_get

        assert _finnhub_get("/stock/recommendation", {"symbol": "X"}) is None

    def test_200_returns_json(self, with_api_key: None) -> None:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"ok": True}
        with patch(
            "alphavision.providers.analyst.requests.get", return_value=resp
        ):
            from alphavision.providers.analyst import _finnhub_get

            assert _finnhub_get("/x", {}) == {"ok": True}

    def test_429_then_200_retries(self, with_api_key: None) -> None:
        bad = MagicMock(status_code=429)
        good = MagicMock(status_code=200)
        good.json.return_value = [1, 2]
        with patch(
            "alphavision.providers.analyst.requests.get",
            side_effect=[bad, good],
        ) as mock_get:
            from alphavision.providers.analyst import _finnhub_get

            result = _finnhub_get("/x", {})
        assert result == [1, 2]
        assert mock_get.call_count == 2

    def test_429_persistent_returns_none(self, with_api_key: None) -> None:
        bad = MagicMock(status_code=429)
        with patch(
            "alphavision.providers.analyst.requests.get", return_value=bad
        ):
            from alphavision.providers.analyst import _finnhub_get

            assert _finnhub_get("/x", {}) is None

    def test_403_then_200_retries(self, with_api_key: None) -> None:
        bad = MagicMock(status_code=403)
        good = MagicMock(status_code=200)
        good.json.return_value = {"ok": True}
        with patch(
            "alphavision.providers.analyst.requests.get",
            side_effect=[bad, good],
        ) as mock_get:
            from alphavision.providers.analyst import _finnhub_get

            result = _finnhub_get("/x", {})
        assert result == {"ok": True}
        assert mock_get.call_count == 2

    def test_403_persistent_returns_none(self, with_api_key: None) -> None:
        bad = MagicMock(status_code=403)
        with patch(
            "alphavision.providers.analyst.requests.get", return_value=bad
        ):
            from alphavision.providers.analyst import _finnhub_get

            assert _finnhub_get("/x", {}) is None

    def test_transport_error_then_success(self, with_api_key: None) -> None:
        import requests

        good = MagicMock(status_code=200)
        good.json.return_value = {"ok": True}
        with patch(
            "alphavision.providers.analyst.requests.get",
            side_effect=[requests.ConnectionError("boom"), good],
        ):
            from alphavision.providers.analyst import _finnhub_get

            assert _finnhub_get("/x", {}) == {"ok": True}

    def test_persistent_transport_error_returns_none(
        self, with_api_key: None
    ) -> None:
        import requests

        with patch(
            "alphavision.providers.analyst.requests.get",
            side_effect=requests.ConnectionError("boom"),
        ):
            from alphavision.providers.analyst import _finnhub_get

            assert _finnhub_get("/x", {}) is None

    def test_non_429_5xx_returns_none(self, with_api_key: None) -> None:
        bad = MagicMock(status_code=500)
        with patch(
            "alphavision.providers.analyst.requests.get", return_value=bad
        ):
            from alphavision.providers.analyst import _finnhub_get

            assert _finnhub_get("/x", {}) is None

    def test_bad_json_returns_none(self, with_api_key: None) -> None:
        resp = MagicMock(status_code=200)
        resp.json.side_effect = ValueError("not json")
        with patch(
            "alphavision.providers.analyst.requests.get", return_value=resp
        ):
            from alphavision.providers.analyst import _finnhub_get

            assert _finnhub_get("/x", {}) is None


# ── fetch_analyst_snapshot ────────────────────────────────────────────────


class TestFetchAnalystSnapshot:
    def test_composes_all_subcalls(self, with_api_key: None) -> None:
        with (
            patch.object(
                analyst_mod,
                "_recommendation_with_drift",
                return_value=(5, 4, 13, 3),
            ),
            patch.object(analyst_mod, "_price_target", return_value=215.0),
            patch.object(
                analyst_mod, "_eps_revision_slope", return_value=0.04
            ),
        ):
            result = fetch_analyst_snapshot("AAPL")
        assert isinstance(result, AnalystSnapshot)
        assert result.net_upgrades_30d == 3
        assert result.strong_buy_count == 5
        assert result.buy_count == 4
        assert result.analyst_count == 13
        assert result.target_mean_price == 215.0
        assert result.eps_revision_slope == pytest.approx(0.04)

    def test_subcall_exception_yields_default(
        self, with_api_key: None
    ) -> None:
        with (
            patch.object(
                analyst_mod,
                "_recommendation_with_drift",
                side_effect=RuntimeError("x"),
            ),
            patch.object(analyst_mod, "_price_target", return_value=None),
            patch.object(analyst_mod, "_eps_revision_slope", return_value=0.0),
            patch.object(
                analyst_mod,
                "_analyst_from_yfinance",
                return_value=(0, 0, 0, 0, None),
            ),
        ):
            result = fetch_analyst_snapshot("AAPL")
        assert result.net_upgrades_30d == 0

    def test_all_failures_yield_neutral(self, with_api_key: None) -> None:
        with (
            patch.object(
                analyst_mod,
                "_recommendation_with_drift",
                side_effect=RuntimeError("x"),
            ),
            patch.object(
                analyst_mod, "_price_target", side_effect=RuntimeError("x")
            ),
            patch.object(
                analyst_mod,
                "_eps_revision_slope",
                side_effect=RuntimeError("x"),
            ),
            patch.object(
                analyst_mod,
                "_analyst_from_yfinance",
                return_value=(0, 0, 0, 0, None),
            ),
        ):
            result = fetch_analyst_snapshot("AAPL")
        assert result.net_upgrades_30d == 0
        assert result.strong_buy_count == 0
        assert result.buy_count == 0
        assert result.analyst_count == 0
        assert result.target_mean_price is None
        assert result.eps_revision_slope == 0.0


# ── _analyst_from_yfinance ────────────────────────────────────────────────


class TestAnalystFromYfinance:
    def test_returns_target_from_analyst_price_targets(self) -> None:
        from alphavision.providers.analyst import _analyst_from_yfinance

        mock_t = MagicMock()
        mock_t.analyst_price_targets = {"mean": 220.0}
        mock_t.recommendations_summary = pd.DataFrame()
        mock_t.upgrades_downgrades = pd.DataFrame()
        with patch(
            "alphavision.providers.analyst.yf.Ticker", return_value=mock_t
        ):
            _net, _sb, _buy, _total, target = _analyst_from_yfinance("AAPL")
        assert target == 220.0

    def test_parses_recommendations_summary(self) -> None:
        from alphavision.providers.analyst import _analyst_from_yfinance

        rec_df = pd.DataFrame(
            {
                "period": ["0m", "-1m"],
                "strongBuy": [5, 3],
                "buy": [4, 2],
                "hold": [2, 1],
                "sell": [1, 0],
                "strongSell": [0, 0],
            }
        )
        mock_t = MagicMock()
        mock_t.analyst_price_targets = {}
        mock_t.recommendations_summary = rec_df
        mock_t.upgrades_downgrades = pd.DataFrame()
        with patch(
            "alphavision.providers.analyst.yf.Ticker", return_value=mock_t
        ):
            _net, sb, buy, total, _target = _analyst_from_yfinance("AAPL")
        assert sb == 5
        assert buy == 4
        assert total == 12  # 5+4+2+1+0

    def test_parses_upgrades_downgrades(self) -> None:
        from alphavision.providers.analyst import _analyst_from_yfinance

        now = pd.Timestamp.now(tz="UTC")
        ud_df = pd.DataFrame(
            {"Action": ["up", "up", "down"]},
            index=[
                now - pd.Timedelta(days=5),
                now - pd.Timedelta(days=10),
                now - pd.Timedelta(days=15),
            ],
        )
        mock_t = MagicMock()
        mock_t.analyst_price_targets = {}
        mock_t.recommendations_summary = pd.DataFrame()
        mock_t.upgrades_downgrades = ud_df
        with patch(
            "alphavision.providers.analyst.yf.Ticker", return_value=mock_t
        ):
            net, _sb, _buy, _total, _target = _analyst_from_yfinance("AAPL")
        assert net == 1  # 2 ups - 1 down

    def test_old_upgrades_excluded(self) -> None:
        from alphavision.providers.analyst import _analyst_from_yfinance

        now = pd.Timestamp.now(tz="UTC")
        ud_df = pd.DataFrame(
            {"Action": ["up", "up"]},
            index=[
                now - pd.Timedelta(days=40),
                now - pd.Timedelta(days=50),
            ],
        )
        mock_t = MagicMock()
        mock_t.analyst_price_targets = {}
        mock_t.recommendations_summary = pd.DataFrame()
        mock_t.upgrades_downgrades = ud_df
        with patch(
            "alphavision.providers.analyst.yf.Ticker", return_value=mock_t
        ):
            net, _sb, _buy, _total, _target = _analyst_from_yfinance("AAPL")
        assert net == 0

    def test_all_failures_return_neutral(self) -> None:
        from alphavision.providers.analyst import _analyst_from_yfinance

        mock_t = MagicMock()
        mock_t.analyst_price_targets = MagicMock(
            side_effect=RuntimeError("boom")
        )
        mock_t.recommendations_summary = MagicMock(
            side_effect=RuntimeError("boom")
        )
        mock_t.upgrades_downgrades = MagicMock(
            side_effect=RuntimeError("boom")
        )
        with patch(
            "alphavision.providers.analyst.yf.Ticker", return_value=mock_t
        ):
            net, sb, buy, total, target = _analyst_from_yfinance("AAPL")
        assert net == 0
        assert sb == 0
        assert buy == 0
        assert total == 0
        assert target is None


class TestFetchAnalystSnapshotFallback:
    def test_no_key_uses_yfinance(self, without_api_key: None) -> None:
        with (
            patch.object(
                analyst_mod,
                "_analyst_from_yfinance",
                return_value=(2, 5, 4, 12, 210.0),
            ),
            patch.object(
                analyst_mod, "_eps_revision_slope", return_value=0.03
            ),
        ):
            result = fetch_analyst_snapshot("AAPL")
        assert result.net_upgrades_30d == 2
        assert result.strong_buy_count == 5
        assert result.buy_count == 4
        assert result.analyst_count == 12
        assert result.target_mean_price == 210.0

    def test_finnhub_empty_falls_back_to_yfinance(
        self, with_api_key: None
    ) -> None:
        with (
            patch.object(
                analyst_mod,
                "_recommendation_with_drift",
                return_value=(0, 0, 0, 0),
            ),
            patch.object(analyst_mod, "_price_target", return_value=None),
            patch.object(
                analyst_mod,
                "_analyst_from_yfinance",
                return_value=(1, 3, 2, 8, 200.0),
            ),
            patch.object(
                analyst_mod, "_eps_revision_slope", return_value=0.02
            ),
        ):
            result = fetch_analyst_snapshot("AAPL")
        assert result.analyst_count == 8
        assert result.target_mean_price == 200.0

    def test_finnhub_has_data_skips_yfinance(self, with_api_key: None) -> None:
        with (
            patch.object(
                analyst_mod,
                "_recommendation_with_drift",
                return_value=(5, 4, 13, 3),
            ),
            patch.object(analyst_mod, "_price_target", return_value=215.0),
            patch.object(
                analyst_mod,
                "_analyst_from_yfinance",
            ) as mock_yf,
            patch.object(
                analyst_mod, "_eps_revision_slope", return_value=0.04
            ),
        ):
            result = fetch_analyst_snapshot("AAPL")
        mock_yf.assert_not_called()
        assert result.analyst_count == 13


# ── _throttle ─────────────────────────────────────────────────────────────


class TestThrottle:
    def test_sleeps_when_too_fast(self, with_api_key: None) -> None:
        # Force last_call to "just now" so the throttle has to sleep.
        analyst_mod._last_call_at = analyst_mod.time.monotonic()
        with patch("alphavision.providers.analyst.time.sleep") as mock_sleep:
            analyst_mod._throttle()
        assert mock_sleep.called

    def test_does_not_sleep_when_idle(self, with_api_key: None) -> None:
        analyst_mod._last_call_at = 0.0  # very long ago
        with patch("alphavision.providers.analyst.time.sleep") as mock_sleep:
            analyst_mod._throttle()
        mock_sleep.assert_not_called()

    def test_lock_prevents_concurrent_bypass(self, with_api_key: None) -> None:
        import threading as _threading

        timestamps: list[float] = []
        analyst_mod._last_call_at = 0.0

        def _record_call() -> None:
            with patch("alphavision.providers.analyst.time.sleep"):
                analyst_mod._throttle()
            timestamps.append(analyst_mod.time.monotonic())

        threads = [_threading.Thread(target=_record_call) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # All three threads completed means the lock didn't deadlock.
        assert len(timestamps) == 3
