# Changelog

All notable changes to AlphaVision Equity Terminal will be documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Changed
- `src/alphavision/data_fetcher.py`: `fetch_universe` now fetches tickers in parallel via `ThreadPoolExecutor` (default 5 workers), reducing wall-clock time for ~520 tickers by ~5×; input order is preserved
- `src/alphavision/data_fetcher.py`: replace per-ticker retry with batch retry loop — rate-limited tickers are retried as a group after a growing cooldown (8 s × round), guaranteeing all tickers are fetched; default workers reduced to 3 to lower rate-limit pressure
- `app.py`: Analysis tab replaced sequential per-ticker loop with parallel `fetch_universe` call inside `st.spinner`

### Added
- `src/alphavision/filters.py`: Dual-Track filtering engine — `passes_turnaround`, `passes_momentum`, `apply_dual_track`
- `src/alphavision/scoring.py`: Conviction Score engine — four-factor scoring (upside gap 40%, rating drift 30%, consensus 20%, EPS momentum 10%) and `rank_candidates` returning Top 20
- `tests/test_filters.py`: 22 tests, 100% filters module coverage
- `tests/test_scoring.py`: 48 tests, 100% scoring module coverage
- `docs/filters.md`: API reference for the filters module
- `docs/scoring.md`: API reference for the scoring module
- `src/alphavision/models.py`: Pydantic `TickerData` model (current price, 6-month metrics, SMA-200, analyst consensus fields)
- `src/alphavision/models.py`: added `ScoredTicker` model with all conviction score fields and channel assignment
- `src/alphavision/data_fetcher.py`: yfinance wrapper — `fetch_ticker()` and `fetch_universe()` with graceful per-ticker error handling
- `tests/test_data_fetcher.py`: 40 tests at 97% module coverage; all yfinance calls mocked
- `docs/data_fetcher.md`: API reference for the data fetcher module
- `pyproject.toml`: added `[[tool.mypy.overrides]]` to suppress yfinance import-untyped errors

### Changed
- `src/alphavision/models.py`: added `company: str = ""` field to `TickerData` (populated from yfinance longName)
- `src/alphavision/data_fetcher.py`: populate `company` field from `info["longName"]`, falling back to ticker symbol
- `app.py`: added Analysis tab with Dual-Track filter stats and Top 20 Conviction Score ranking table

### Changed
- `pyproject.toml`: project bootstrap with hatchling, ruff, mypy, pytest config
- `src/alphavision/__init__.py`: package entry point
- `src/alphavision/universe.py`: S&P 500 + Nasdaq-100 universe builder via Wikipedia Action API
- `app.py`: Streamlit MVP UI displaying the ~520-ticker equity universe
- `docs/universe.md`: API reference for the universe module
- `README.md`: project quick-start, structure, and learning resources

### Changed
- `src/alphavision/universe.py`: switched from `pd.read_html(url)` to Wikipedia Action API to avoid 403 rate-limit; added `_fetch_wikipedia_html`, column dedup guard for NDX100 `ICB Subsector` column
- `CLAUDE.md`: added Gate 6 (Streamlit smoke test), English-only rule, docs-in-`docs/` rule, virtual environment clarification, README mandatory update rule
- `docs/CUSTOMIZATIONS.md`: updated goal coverage matrix with new rules
- `README.md`: updated project structure to reflect `docs/` reorganization

### Moved to `docs/`
- `CUSTOMIZATIONS.md` → `docs/CUSTOMIZATIONS.md`
- `SAD.md` → `docs/SAD.md`
- `METADOLOGY.md` → `docs/METADOLOGY.md`
- `ROADMAP.md` → `docs/ROADMAP.md`
