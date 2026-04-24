"""Tests for alphavision.universe."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest
import requests

from alphavision.universe import build_universe, get_nasdaq100, get_sp500

# ── Shared test data ───────────────────────────────────────────────────────

_DUMMY_HTML = "<html><body>mocked</body></html>"


def _make_sp500_raw() -> pd.DataFrame:
    """Raw Wikipedia-style DataFrame before column renaming."""
    return pd.DataFrame(
        {
            "Symbol": ["AAPL", "MSFT", "GOOGL"],
            "Security": ["Apple Inc.", "Microsoft Corp.", "Alphabet Inc."],
            "GICS Sector": ["Technology", "Technology", "Communication"],
            "Extra": ["x", "x", "x"],
        }
    )


def _make_ndx100_raw() -> pd.DataFrame:
    """Raw Wikipedia-style DataFrame before column renaming."""
    return pd.DataFrame(
        {
            "Ticker": ["AAPL", "AMZN", "META"],
            "Company": ["Apple Inc.", "Amazon.com Inc.", "Meta Platforms"],
            "Sector": ["Technology", "Consumer Disc.", "Communication"],
        }
    )


def _make_sp500_processed() -> pd.DataFrame:
    """Already-processed DataFrame as returned by get_sp500()."""
    return pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT", "GOOGL"],
            "company": ["Apple Inc.", "Microsoft Corp.", "Alphabet Inc."],
            "sector": ["Technology", "Technology", "Communication"],
        }
    )


def _make_ndx100_processed() -> pd.DataFrame:
    """Already-processed DataFrame as returned by get_nasdaq100()."""
    return pd.DataFrame(
        {
            "ticker": ["AAPL", "AMZN", "META"],
            "company": ["Apple Inc.", "Amazon.com Inc.", "Meta Platforms"],
            "sector": ["Technology", "Consumer Disc.", "Communication"],
        }
    )


# ── get_sp500 happy path ───────────────────────────────────────────────────


class TestGetSp500HappyPath:
    def test_returns_dataframe(self) -> None:
        with (
            patch(
                "alphavision.universe._fetch_wikipedia_html",
                return_value=_DUMMY_HTML,
            ),
            patch(
                "alphavision.universe.pd.read_html",
                return_value=[_make_sp500_raw()],
            ),
        ):
            result = get_sp500()
        assert isinstance(result, pd.DataFrame)

    def test_columns_are_ticker_company_sector(self) -> None:
        with (
            patch(
                "alphavision.universe._fetch_wikipedia_html",
                return_value=_DUMMY_HTML,
            ),
            patch(
                "alphavision.universe.pd.read_html",
                return_value=[_make_sp500_raw()],
            ),
        ):
            result = get_sp500()
        assert list(result.columns) == ["ticker", "company", "sector"]

    def test_row_count_matches_source(self) -> None:
        with (
            patch(
                "alphavision.universe._fetch_wikipedia_html",
                return_value=_DUMMY_HTML,
            ),
            patch(
                "alphavision.universe.pd.read_html",
                return_value=[_make_sp500_raw()],
            ),
        ):
            result = get_sp500()
        assert len(result) == 3

    def test_dot_in_ticker_replaced_with_dash(self) -> None:
        df = _make_sp500_raw()
        df.loc[0, "Symbol"] = "BRK.B"
        with (
            patch(
                "alphavision.universe._fetch_wikipedia_html",
                return_value=_DUMMY_HTML,
            ),
            patch("alphavision.universe.pd.read_html", return_value=[df]),
        ):
            result = get_sp500()
        assert "BRK-B" in result["ticker"].values


# ── get_sp500 error cases ──────────────────────────────────────────────────


class TestGetSp500Errors:
    def test_http_403_raises_runtime_error(self) -> None:
        with patch(
            "alphavision.universe._fetch_wikipedia_html",
            side_effect=requests.HTTPError("403 Forbidden"),
        ):
            with pytest.raises(RuntimeError, match="Failed to fetch S&P 500"):
                get_sp500()

    def test_parse_error_raises_runtime_error(self) -> None:
        with (
            patch(
                "alphavision.universe._fetch_wikipedia_html",
                return_value=_DUMMY_HTML,
            ),
            patch(
                "alphavision.universe.pd.read_html",
                side_effect=ValueError("bad html"),
            ),
        ):
            with pytest.raises(RuntimeError, match="Failed to fetch S&P 500"):
                get_sp500()

    def test_empty_table_list_raises_runtime_error(self) -> None:
        with (
            patch(
                "alphavision.universe._fetch_wikipedia_html",
                return_value=_DUMMY_HTML,
            ),
            patch(
                "alphavision.universe.pd.read_html",
                return_value=[],
            ),
        ):
            with pytest.raises(RuntimeError, match="No tables found"):
                get_sp500()


# ── get_nasdaq100 happy path ───────────────────────────────────────────────


class TestGetNasdaq100HappyPath:
    def test_returns_dataframe(self) -> None:
        with (
            patch(
                "alphavision.universe._fetch_wikipedia_html",
                return_value=_DUMMY_HTML,
            ),
            patch(
                "alphavision.universe.pd.read_html",
                return_value=[_make_ndx100_raw()],
            ),
        ):
            result = get_nasdaq100()
        assert isinstance(result, pd.DataFrame)

    def test_columns_are_ticker_company_sector(self) -> None:
        with (
            patch(
                "alphavision.universe._fetch_wikipedia_html",
                return_value=_DUMMY_HTML,
            ),
            patch(
                "alphavision.universe.pd.read_html",
                return_value=[_make_ndx100_raw()],
            ),
        ):
            result = get_nasdaq100()
        assert list(result.columns) == ["ticker", "company", "sector"]

    def test_row_count_matches_source(self) -> None:
        with (
            patch(
                "alphavision.universe._fetch_wikipedia_html",
                return_value=_DUMMY_HTML,
            ),
            patch(
                "alphavision.universe.pd.read_html",
                return_value=[_make_ndx100_raw()],
            ),
        ):
            result = get_nasdaq100()
        assert len(result) == 3

    def test_missing_sector_column_fills_empty_string(self) -> None:
        df = _make_ndx100_raw().drop(columns=["Sector"])
        with (
            patch(
                "alphavision.universe._fetch_wikipedia_html",
                return_value=_DUMMY_HTML,
            ),
            patch("alphavision.universe.pd.read_html", return_value=[df]),
        ):
            result = get_nasdaq100()
        assert "sector" in result.columns
        assert (result["sector"] == "").all()


# ── get_nasdaq100 error cases ──────────────────────────────────────────────


class TestGetNasdaq100Errors:
    def test_http_403_raises_runtime_error(self) -> None:
        with patch(
            "alphavision.universe._fetch_wikipedia_html",
            side_effect=requests.HTTPError("403 Forbidden"),
        ):
            with pytest.raises(
                RuntimeError, match="Failed to fetch Nasdaq-100"
            ):
                get_nasdaq100()

    def test_parse_error_raises_runtime_error(self) -> None:
        with (
            patch(
                "alphavision.universe._fetch_wikipedia_html",
                return_value=_DUMMY_HTML,
            ),
            patch(
                "alphavision.universe.pd.read_html",
                side_effect=OSError("network error"),
            ),
        ):
            with pytest.raises(
                RuntimeError, match="Failed to fetch Nasdaq-100"
            ):
                get_nasdaq100()

    def test_empty_table_list_raises_runtime_error(self) -> None:
        with (
            patch(
                "alphavision.universe._fetch_wikipedia_html",
                return_value=_DUMMY_HTML,
            ),
            patch(
                "alphavision.universe.pd.read_html",
                return_value=[],
            ),
        ):
            with pytest.raises(RuntimeError, match="No tables found"):
                get_nasdaq100()


# ── build_universe happy path ──────────────────────────────────────────────


class TestBuildUniverseHappyPath:
    """Mock get_sp500/get_nasdaq100 directly to isolate build logic."""

    def _run(self) -> pd.DataFrame:
        with (
            patch(
                "alphavision.universe.get_sp500",
                return_value=_make_sp500_processed(),
            ),
            patch(
                "alphavision.universe.get_nasdaq100",
                return_value=_make_ndx100_processed(),
            ),
            patch("alphavision.universe.time.sleep"),
        ):
            return build_universe()

    def test_returns_dataframe(self) -> None:
        assert isinstance(self._run(), pd.DataFrame)

    def test_columns_include_source(self) -> None:
        assert "source" in self._run().columns

    def test_ticker_in_both_indices_labeled_both(self) -> None:
        result = self._run()
        aapl = result[result["ticker"] == "AAPL"]
        assert len(aapl) == 1
        assert aapl.iloc[0]["source"] == "BOTH"

    def test_sp500_only_ticker_labeled_sp500(self) -> None:
        result = self._run()
        msft = result[result["ticker"] == "MSFT"]
        assert msft.iloc[0]["source"] == "SP500"

    def test_ndx100_only_ticker_labeled_ndx100(self) -> None:
        result = self._run()
        amzn = result[result["ticker"] == "AMZN"]
        assert amzn.iloc[0]["source"] == "NDX100"

    def test_no_duplicate_tickers(self) -> None:
        assert self._run()["ticker"].is_unique

    def test_sorted_alphabetically_by_ticker(self) -> None:
        tickers = self._run()["ticker"].tolist()
        assert tickers == sorted(tickers)

    def test_total_count_is_union_of_both_indices(self) -> None:
        result = self._run()
        # SP500: AAPL, MSFT, GOOGL — NDX100: AAPL, AMZN, META
        # Union: AAPL, AMZN, GOOGL, META, MSFT = 5
        assert len(result) == 5


# ── _fetch_wikipedia_html unit ────────────────────────────────────────────


class TestFetchWikipediaHtml:
    def test_returns_parsed_html_from_api_response(self) -> None:
        from unittest.mock import MagicMock

        from alphavision.universe import _fetch_wikipedia_html

        api_payload = {"parse": {"text": {"*": "<html>wiki content</html>"}}}
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_payload
        with patch(
            "alphavision.universe.requests.get", return_value=mock_resp
        ):
            result = _fetch_wikipedia_html("Nasdaq-100")
        assert result == "<html>wiki content</html>"
        mock_resp.raise_for_status.assert_called_once()

    def test_api_error_raises_runtime_error(self) -> None:
        from unittest.mock import MagicMock

        from alphavision.universe import _fetch_wikipedia_html

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": {"info": "page not found"}}
        with patch(
            "alphavision.universe.requests.get", return_value=mock_resp
        ):
            with pytest.raises(RuntimeError, match="Wikipedia API error"):
                _fetch_wikipedia_html("NonExistentPage")


# ── build_universe error propagation ──────────────────────────────────────


class TestBuildUniverseErrors:
    def test_sp500_fetch_failure_propagates_runtime_error(self) -> None:
        with patch(
            "alphavision.universe._fetch_wikipedia_html",
            side_effect=OSError("connection refused"),
        ):
            with pytest.raises(RuntimeError):
                build_universe()
