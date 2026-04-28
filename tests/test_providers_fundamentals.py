"""Tests for alphavision.providers.fundamentals."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import alphavision.providers.fundamentals as fund_mod
from alphavision.providers.fundamentals import (
    FundamentalsSnapshot,
    _compute_metrics,
    _first_present,
    _xbrl_facts,
    fetch_fundamentals_snapshot,
)


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path: Path) -> Generator[None]:
    """Point the cache at a tmp directory and reset the identity flag."""
    fund_mod._identity_set = False
    cache_dir = tmp_path / "data"
    cache_db = cache_dir / "fundamentals_cache.db"
    with (
        patch.object(fund_mod, "_CACHE_DIR", cache_dir),
        patch.object(fund_mod, "_CACHE_DB", cache_db),
    ):
        yield


# ── _first_present ────────────────────────────────────────────────────────


class TestFirstPresent:
    def test_returns_first_match(self) -> None:
        assert _first_present({"B": 2.0, "A": 1.0}, ("A", "B")) == 1.0

    def test_falls_through(self) -> None:
        assert _first_present({"B": 2.0}, ("A", "B")) == 2.0

    def test_none_when_missing(self) -> None:
        assert _first_present({}, ("A",)) is None


# ── _compute_metrics ──────────────────────────────────────────────────────


class TestComputeMetrics:
    def test_happy_path(self) -> None:
        facts_now = {
            "Revenues": 110_000_000.0,
            "NetCashProvidedByUsedInOperatingActivities": 30_000_000.0,
            "PaymentsToAcquirePropertyPlantAndEquipment": 5_000_000.0,
            "NetIncomeLoss": 20_000_000.0,
        }
        facts_prior = {"Revenues": 100_000_000.0}
        r40, eq = _compute_metrics(facts_now, facts_prior)
        # Rev growth = 10%, FCF = 25M, FCF margin = 25/110 ≈ 22.7%
        assert r40 == pytest.approx(10.0 + 25_000_000 / 110_000_000 * 100)
        # Earnings quality = 25M / 20M = 1.25
        assert eq == pytest.approx(1.25)

    def test_missing_capex_blocks_fcf(self) -> None:
        facts_now = {
            "Revenues": 100_000_000.0,
            "NetCashProvidedByUsedInOperatingActivities": 30_000_000.0,
            "NetIncomeLoss": 10_000_000.0,
        }
        r40, eq = _compute_metrics(facts_now, {"Revenues": 95_000_000.0})
        assert r40 is None
        assert eq is None

    def test_missing_revenue_blocks_growth_and_margin(self) -> None:
        facts_now = {
            "NetCashProvidedByUsedInOperatingActivities": 30_000_000.0,
            "PaymentsToAcquirePropertyPlantAndEquipment": 5_000_000.0,
            "NetIncomeLoss": 10_000_000.0,
        }
        r40, eq = _compute_metrics(facts_now, {})
        assert r40 is None  # FCF margin denominator missing
        # Earnings quality still computes since FCF (25M) and NetIncome ok.
        assert eq == pytest.approx(2.5)

    def test_missing_prior_revenue_blocks_growth(self) -> None:
        facts_now = {
            "Revenues": 110_000_000.0,
            "NetCashProvidedByUsedInOperatingActivities": 30_000_000.0,
            "PaymentsToAcquirePropertyPlantAndEquipment": 5_000_000.0,
            "NetIncomeLoss": 20_000_000.0,
        }
        r40, eq = _compute_metrics(facts_now, {})
        assert r40 is None  # no growth without prior revenue
        assert eq == pytest.approx(1.25)

    def test_zero_net_income_yields_none_earnings_quality(self) -> None:
        facts_now = {
            "Revenues": 100_000_000.0,
            "NetCashProvidedByUsedInOperatingActivities": 20_000_000.0,
            "PaymentsToAcquirePropertyPlantAndEquipment": 4_000_000.0,
            "NetIncomeLoss": 0.0,
        }
        r40, eq = _compute_metrics(facts_now, {"Revenues": 95_000_000.0})
        assert eq is None
        assert r40 is not None

    def test_alternate_revenue_tag(self) -> None:
        facts_now = {
            "RevenueFromContractWithCustomerExcludingAssessedTax": 1_000.0,
            "NetCashProvidedByOperatingActivities": 200.0,
            "PaymentsToAcquireProductiveAssets": 50.0,
            "ProfitLoss": 100.0,
        }
        facts_prior = {
            "RevenueFromContractWithCustomerExcludingAssessedTax": 800.0,
        }
        r40, eq = _compute_metrics(facts_now, facts_prior)
        # Rev growth = 25%, FCF = 150, margin = 15%, R40 = 40%
        assert r40 == pytest.approx(40.0)
        assert eq == pytest.approx(1.5)


# ── _xbrl_facts ───────────────────────────────────────────────────────────


def _fact(concept: str, value: float | str | None) -> MagicMock:
    f = MagicMock()
    f.concept = concept
    f.tag = None
    f.name = None
    f.value = value
    f.numeric = None
    return f


class TestXbrlFacts:
    def test_normalises_tags_and_values(self) -> None:
        filing = MagicMock()
        xb = MagicMock()
        xb.facts = [
            _fact("us-gaap:Revenues", 1000.0),
            _fact("us-gaap:NetIncomeLoss", 100.0),
        ]
        filing.xbrl.return_value = xb
        out = _xbrl_facts(filing)
        assert out["Revenues"] == 1000.0
        assert out["NetIncomeLoss"] == 100.0

    def test_skips_unparseable_values(self) -> None:
        filing = MagicMock()
        xb = MagicMock()
        xb.facts = [
            _fact("us-gaap:Revenues", "not-a-number"),
            _fact("us-gaap:NetIncomeLoss", 100.0),
        ]
        filing.xbrl.return_value = xb
        out = _xbrl_facts(filing)
        assert "Revenues" not in out
        assert out["NetIncomeLoss"] == 100.0

    def test_first_occurrence_wins(self) -> None:
        filing = MagicMock()
        xb = MagicMock()
        xb.facts = [
            _fact("us-gaap:Revenues", 1000.0),
            _fact("us-gaap:Revenues", 999.0),
        ]
        filing.xbrl.return_value = xb
        out = _xbrl_facts(filing)
        assert out["Revenues"] == 1000.0

    def test_empty_facts(self) -> None:
        filing = MagicMock()
        xb = MagicMock()
        xb.facts = []
        filing.xbrl.return_value = xb
        assert _xbrl_facts(filing) == {}

    def test_xbrl_none_returns_empty(self) -> None:
        filing = MagicMock()
        filing.xbrl.return_value = None
        assert _xbrl_facts(filing) == {}

    def test_xbrl_raises_returns_empty(self) -> None:
        filing = MagicMock()
        filing.xbrl.side_effect = RuntimeError("boom")
        assert _xbrl_facts(filing) == {}

    def test_facts_attr_missing(self) -> None:
        filing = MagicMock()
        xb = MagicMock(spec=[])  # no `facts`
        filing.xbrl.return_value = xb
        assert _xbrl_facts(filing) == {}


# ── Cache layer ───────────────────────────────────────────────────────────


class TestCache:
    def test_put_then_get(self) -> None:
        fund_mod._cache_put("AAPL", "0001", {"rule_of_40": 42.0})
        assert fund_mod._cache_get("AAPL", "0001") == {"rule_of_40": 42.0}

    def test_get_missing_returns_none(self) -> None:
        assert fund_mod._cache_get("AAPL", "missing") is None

    def test_overwrite_replaces_value(self) -> None:
        fund_mod._cache_put("AAPL", "0001", {"rule_of_40": 42.0})
        fund_mod._cache_put("AAPL", "0001", {"rule_of_40": 50.0})
        assert fund_mod._cache_get("AAPL", "0001") == {"rule_of_40": 50.0}


# ── fetch_fundamentals_snapshot ───────────────────────────────────────────


class TestFetchFundamentalsSnapshot:
    def test_no_filing_returns_neutral(self) -> None:
        with (
            patch.object(fund_mod, "_latest_accession", return_value=None),
            patch.object(
                fund_mod,
                "_yfinance_fundamentals_snapshot",
                return_value=FundamentalsSnapshot(ticker="XYZ"),
            ),
        ):
            result = fetch_fundamentals_snapshot("XYZ")
        assert isinstance(result, FundamentalsSnapshot)
        assert result.rule_of_40 is None
        assert result.earnings_quality is None

    def test_cache_hit_short_circuits(self) -> None:
        filing = MagicMock()
        with patch.object(
            fund_mod, "_latest_accession", return_value=("ACC1", filing)
        ):
            fund_mod._cache_put(
                "AAPL", "ACC1", {"rule_of_40": 50.0, "earnings_quality": 1.5}
            )
            with (
                patch.object(fund_mod, "_xbrl_facts") as facts_mock,
                patch.object(fund_mod, "_prior_year_facts") as prior_mock,
            ):
                result = fetch_fundamentals_snapshot("AAPL")
            facts_mock.assert_not_called()
            prior_mock.assert_not_called()
        assert result.rule_of_40 == 50.0
        assert result.earnings_quality == 1.5

    def test_cache_miss_computes_and_writes(self) -> None:
        filing = MagicMock()
        with (
            patch.object(
                fund_mod, "_latest_accession", return_value=("ACC2", filing)
            ),
            patch.object(
                fund_mod,
                "_xbrl_facts",
                return_value={
                    "Revenues": 110.0,
                    "NetCashProvidedByUsedInOperatingActivities": 30.0,
                    "PaymentsToAcquirePropertyPlantAndEquipment": 5.0,
                    "NetIncomeLoss": 20.0,
                },
            ),
            patch.object(
                fund_mod,
                "_prior_year_facts",
                return_value={"Revenues": 100.0},
            ),
        ):
            result = fetch_fundamentals_snapshot("AAPL")
        assert result.rule_of_40 is not None
        assert result.earnings_quality == pytest.approx(1.25)
        assert fund_mod._cache_get("AAPL", "ACC2") is not None

    def test_xbrl_exception_yields_empty_facts(self) -> None:
        filing = MagicMock()
        with (
            patch.object(
                fund_mod, "_latest_accession", return_value=("ACC3", filing)
            ),
            patch.object(
                fund_mod, "_xbrl_facts", side_effect=RuntimeError("boom")
            ),
            patch.object(fund_mod, "_prior_year_facts", return_value={}),
            patch.object(
                fund_mod,
                "_yfinance_fundamentals_snapshot",
                return_value=FundamentalsSnapshot(ticker="XYZ"),
            ),
        ):
            result = fetch_fundamentals_snapshot("XYZ")
        assert result.rule_of_40 is None
        assert result.earnings_quality is None


# ── _latest_accession (integration with mocked edgar) ─────────────────────


def _mock_edgar(company_mock: MagicMock | None = None) -> MagicMock:
    """Return a MagicMock edgar module, injected via sys.modules to avoid
    importing the real package and triggering its DeprecationWarning.
    """
    m = MagicMock()
    if company_mock is not None:
        m.Company = company_mock
    return m


class TestLatestAccession:
    def test_company_construction_failure_returns_none(self) -> None:
        mock_edgar = _mock_edgar()
        mock_edgar.Company.side_effect = RuntimeError("bad symbol")
        with patch.dict(sys.modules, {"edgar": mock_edgar}):
            assert fund_mod._latest_accession("BAD") is None

    def test_no_filings_returns_none(self) -> None:
        company = MagicMock()
        company.get_filings.return_value = None
        mock_edgar = _mock_edgar()
        mock_edgar.Company.return_value = company
        with patch.dict(sys.modules, {"edgar": mock_edgar}):
            assert fund_mod._latest_accession("AAPL") is None

    def test_happy_path_picks_latest(self) -> None:
        latest = MagicMock()
        latest.accession_no = "0001-23-456"
        filings = MagicMock()
        filings.latest.return_value = latest
        company = MagicMock()
        company.get_filings.return_value = filings
        mock_edgar = _mock_edgar()
        mock_edgar.Company.return_value = company
        with patch.dict(sys.modules, {"edgar": mock_edgar}):
            result = fund_mod._latest_accession("AAPL")
        assert result is not None
        assert result[0] == "0001-23-456"

    def test_filing_without_accession_skipped(self) -> None:
        latest = MagicMock(spec=[])  # no accession attrs
        filings = MagicMock()
        filings.latest.return_value = latest
        company = MagicMock()
        company.get_filings.return_value = filings
        mock_edgar = _mock_edgar()
        mock_edgar.Company.return_value = company
        with patch.dict(sys.modules, {"edgar": mock_edgar}):
            assert fund_mod._latest_accession("AAPL") is None


# ── _yfinance_fundamentals_snapshot ──────────────────────────────────────


class TestYfinanceFundamentalsSnapshot:
    def test_happy_path(self) -> None:
        from alphavision.providers.fundamentals import (
            _yfinance_fundamentals_snapshot,
        )

        mock_t = MagicMock()
        mock_t.info = {
            "revenueGrowth": 0.15,
            "freeCashflow": 30_000_000,
            "totalRevenue": 200_000_000,
            "netIncomeToCommon": 20_000_000,
        }
        with patch(
            "alphavision.providers.fundamentals.yf.Ticker",
            return_value=mock_t,
        ):
            result = _yfinance_fundamentals_snapshot("AAPL")
        # rule_of_40 = 15% growth + (30M/200M)*100 = 15 + 15 = 30
        assert result.rule_of_40 == pytest.approx(30.0)
        # earnings_quality = 30M / 20M = 1.5
        assert result.earnings_quality == pytest.approx(1.5)

    def test_missing_revenue_yields_none_rule_of_40(self) -> None:
        from alphavision.providers.fundamentals import (
            _yfinance_fundamentals_snapshot,
        )

        mock_t = MagicMock()
        mock_t.info = {
            "freeCashflow": 10_000_000,
            "netIncomeToCommon": 5_000_000,
        }
        with patch(
            "alphavision.providers.fundamentals.yf.Ticker",
            return_value=mock_t,
        ):
            result = _yfinance_fundamentals_snapshot("AAPL")
        assert result.rule_of_40 is None
        assert result.earnings_quality == pytest.approx(2.0)

    def test_zero_net_income_yields_none_earnings_quality(self) -> None:
        from alphavision.providers.fundamentals import (
            _yfinance_fundamentals_snapshot,
        )

        mock_t = MagicMock()
        mock_t.info = {
            "revenueGrowth": 0.10,
            "freeCashflow": 10_000_000,
            "totalRevenue": 100_000_000,
            "netIncomeToCommon": 0,
        }
        with patch(
            "alphavision.providers.fundamentals.yf.Ticker",
            return_value=mock_t,
        ):
            result = _yfinance_fundamentals_snapshot("AAPL")
        assert result.earnings_quality is None

    def test_info_exception_returns_neutral(self) -> None:
        from alphavision.providers.fundamentals import (
            _yfinance_fundamentals_snapshot,
        )

        mock_t = MagicMock()
        mock_t.info = MagicMock(side_effect=RuntimeError("timeout"))
        with patch(
            "alphavision.providers.fundamentals.yf.Ticker",
            return_value=mock_t,
        ):
            result = _yfinance_fundamentals_snapshot("XYZ")
        assert result.rule_of_40 is None
        assert result.earnings_quality is None

    def test_non_dict_info_returns_neutral(self) -> None:
        from alphavision.providers.fundamentals import (
            _yfinance_fundamentals_snapshot,
        )

        mock_t = MagicMock()
        mock_t.info = None
        with patch(
            "alphavision.providers.fundamentals.yf.Ticker",
            return_value=mock_t,
        ):
            result = _yfinance_fundamentals_snapshot("XYZ")
        assert result.rule_of_40 is None


class TestFetchFundamentalsSnapshotFallback:
    def test_edgar_empty_metrics_triggers_yfinance(self) -> None:
        filing = MagicMock()
        yf_snap = FundamentalsSnapshot(
            ticker="AAPL", rule_of_40=40.0, earnings_quality=1.5
        )
        with (
            patch.object(
                fund_mod,
                "_latest_accession",
                return_value=("ACC_YF", filing),
            ),
            patch.object(fund_mod, "_xbrl_facts", return_value={}),
            patch.object(fund_mod, "_prior_year_facts", return_value={}),
            patch.object(
                fund_mod,
                "_yfinance_fundamentals_snapshot",
                return_value=yf_snap,
            ),
        ):
            result = fetch_fundamentals_snapshot("AAPL")
        assert result.rule_of_40 == pytest.approx(40.0)
        assert result.earnings_quality == pytest.approx(1.5)

    def test_edgar_has_metrics_skips_yfinance(self) -> None:
        filing = MagicMock()
        with (
            patch.object(
                fund_mod,
                "_latest_accession",
                return_value=("ACC_ED", filing),
            ),
            patch.object(
                fund_mod,
                "_xbrl_facts",
                return_value={
                    "Revenues": 110.0,
                    "NetCashProvidedByUsedInOperatingActivities": 30.0,
                    "PaymentsToAcquirePropertyPlantAndEquipment": 5.0,
                    "NetIncomeLoss": 20.0,
                },
            ),
            patch.object(
                fund_mod,
                "_prior_year_facts",
                return_value={"Revenues": 100.0},
            ),
            patch.object(
                fund_mod,
                "_yfinance_fundamentals_snapshot",
            ) as mock_yf,
        ):
            result = fetch_fundamentals_snapshot("AAPL")
        mock_yf.assert_not_called()
        assert result.rule_of_40 is not None
