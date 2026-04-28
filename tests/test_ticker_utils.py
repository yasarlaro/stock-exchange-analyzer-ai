"""Tests for alphavision.ticker_utils."""

from __future__ import annotations

import pandas as pd

from alphavision.ticker_utils import (
    _MAX_TICKERS,
    parse_ticker_input,
    validate_against_universe,
)

# ── parse_ticker_input ────────────────────────────────────────────────────


class TestParseTickerInput:
    def test_empty_string_returns_empty(self) -> None:
        assert parse_ticker_input("") == []

    def test_whitespace_only_returns_empty(self) -> None:
        assert parse_ticker_input("   \n\t  ") == []

    def test_single_ticker(self) -> None:
        assert parse_ticker_input("AAPL") == ["AAPL"]

    def test_normalises_to_uppercase(self) -> None:
        assert parse_ticker_input("aapl") == ["AAPL"]

    def test_comma_separated(self) -> None:
        assert parse_ticker_input("AAPL,MSFT,NVDA") == ["AAPL", "MSFT", "NVDA"]

    def test_space_separated(self) -> None:
        assert parse_ticker_input("AAPL MSFT NVDA") == ["AAPL", "MSFT", "NVDA"]

    def test_semicolon_separated(self) -> None:
        assert parse_ticker_input("AAPL;MSFT;NVDA") == ["AAPL", "MSFT", "NVDA"]

    def test_newline_separated(self) -> None:
        result = parse_ticker_input("AAPL\nMSFT\nNVDA")
        assert result == ["AAPL", "MSFT", "NVDA"]

    def test_mixed_delimiters(self) -> None:
        result = parse_ticker_input("AAPL, msft  NVDA;googl\nMETA")
        assert result == ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]

    def test_deduplication_preserves_first_occurrence(self) -> None:
        result = parse_ticker_input("AAPL MSFT AAPL NVDA MSFT")
        assert result == ["AAPL", "MSFT", "NVDA"]

    def test_extra_whitespace_ignored(self) -> None:
        result = parse_ticker_input("  AAPL   ,   MSFT  ")
        assert result == ["AAPL", "MSFT"]

    def test_dot_in_ticker_preserved(self) -> None:
        result = parse_ticker_input("BRK.B")
        assert result == ["BRK.B"]

    def test_hyphen_in_ticker_preserved(self) -> None:
        result = parse_ticker_input("BF-B")
        assert result == ["BF-B"]

    def test_truncates_at_max(self) -> None:
        big_input = " ".join(f"T{i:04d}" for i in range(_MAX_TICKERS + 10))
        result = parse_ticker_input(big_input)
        assert len(result) == _MAX_TICKERS

    def test_order_preserved(self) -> None:
        result = parse_ticker_input("NVDA,AAPL,MSFT")
        assert result == ["NVDA", "AAPL", "MSFT"]

    def test_numbers_in_ticker_allowed(self) -> None:
        result = parse_ticker_input("T3")
        assert result == ["T3"]


# ── validate_against_universe ─────────────────────────────────────────────


def _df(tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"ticker": tickers})


class TestValidateAgainstUniverse:
    def test_all_in_universe(self) -> None:
        in_uni, out_uni = validate_against_universe(
            ["AAPL", "MSFT"], _df(["AAPL", "MSFT", "NVDA"])
        )
        assert in_uni == ["AAPL", "MSFT"]
        assert out_uni == []

    def test_none_in_universe(self) -> None:
        in_uni, out_uni = validate_against_universe(
            ["XYZ", "ZZZ"], _df(["AAPL", "MSFT"])
        )
        assert in_uni == []
        assert out_uni == ["XYZ", "ZZZ"]

    def test_mixed(self) -> None:
        in_uni, out_uni = validate_against_universe(
            ["AAPL", "XYZ", "MSFT"], _df(["AAPL", "MSFT"])
        )
        assert in_uni == ["AAPL", "MSFT"]
        assert out_uni == ["XYZ"]

    def test_empty_tickers_returns_empty(self) -> None:
        in_uni, out_uni = validate_against_universe([], _df(["AAPL"]))
        assert in_uni == []
        assert out_uni == []

    def test_empty_universe_all_unknown(self) -> None:
        in_uni, out_uni = validate_against_universe(["AAPL"], _df([]))
        assert in_uni == []
        assert out_uni == ["AAPL"]

    def test_case_insensitive_match(self) -> None:
        in_uni, out_uni = validate_against_universe(["aapl"], _df(["AAPL"]))
        assert in_uni == ["aapl"]
        assert out_uni == []

    def test_preserves_input_order(self) -> None:
        in_uni, _ = validate_against_universe(
            ["MSFT", "AAPL", "NVDA"], _df(["AAPL", "MSFT", "NVDA"])
        )
        assert in_uni == ["MSFT", "AAPL", "NVDA"]

    def test_missing_ticker_column_all_unknown(self) -> None:
        bad_df = pd.DataFrame({"name": ["Apple"]})
        in_uni, out_uni = validate_against_universe(["AAPL"], bad_df)
        assert in_uni == []
        assert out_uni == ["AAPL"]

    def test_duplicate_in_universe_df_handled(self) -> None:
        in_uni, out_uni = validate_against_universe(
            ["AAPL"], _df(["AAPL", "AAPL"])
        )
        assert in_uni == ["AAPL"]
        assert out_uni == []
