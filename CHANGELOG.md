# Changelog

All notable changes to AlphaVision Equity Terminal will be documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added — two-phase fetch (3× Finnhub call reduction, ~7–8 min analysis)
- `src/alphavision/providers/prices.py`: `fetch_price_batch()` — single `yf.download()` call for all 511 tickers; `_extract_closes_from_batch()` handles flat and MultiIndex column layouts; `fetch_benchmark_return_12_1()` ETF-safe benchmark helper
- `src/alphavision/providers/analyst.py`: `_recommendation_with_drift()` — derives `net_drift` from month-over-month delta in a single `/stock/recommendation` payload, replacing the separate `/stock/upgrade-downgrade` call (3 → 2 Finnhub calls per ticker)
- `src/alphavision/data_fetcher.py`: `fetch_universe_two_phase()` — Phase 1 batch price-fetch + price-gate pre-filter (~200 survivors from 511); Phase 2 analyst + EDGAR only for survivors; `_passes_price_gate()` applies SMA-200, 12-1 return, and extension cap gates; `_fetch_analyst_and_fundamentals()` Phase 2 worker with per-provider fallback
- `app.py`: Analysis tab switched to `fetch_universe_two_phase()`; funnel metrics (Universe Scanned → Passed Price Gate → Passed Full Gate → Top 20 Ranked → Over-Extended) displayed in Phase 5
- `tests/test_providers_prices.py`: 13 new tests for `_extract_closes_from_batch` and `fetch_price_batch`
- `tests/test_providers_analyst.py`: 6 new tests for `_recommendation_with_drift`; existing `fetch_analyst_snapshot` tests updated to use new 2-call path
- `tests/test_data_fetcher.py`: 14 new tests for `_passes_price_gate`, `fetch_universe_two_phase`, `_fetch_analyst_and_fundamentals`, and `fetch_universe` status_fn branches

### Changed — two-phase fetch
- `src/alphavision/providers/analyst.py`: `fetch_analyst_snapshot` Finnhub path now calls `_recommendation_with_drift` + `_price_target` (2 calls, down from 3); log message updated to `"analyst | TICKER | Finnhub API (2 calls)"`

### Added — Custom Analysis tab
- `app.py`: new "Custom Analysis" tab — users enter up to 50 ticker symbols (any delimiter), the app runs the same Forward-Momentum gate and Conviction Score pipeline on those tickers only, and displays all ranked results (no top-20 cap)
- `src/alphavision/ticker_utils.py`: `parse_ticker_input()` parses comma/space/semicolon/newline-delimited freeform input; `validate_against_universe()` splits tickers into in-universe / unknown (informational, does not block analysis)
- `src/alphavision/scoring.py`: `rank_candidates()` gained a `top_n: int | None` parameter — pass `None` to return all scored candidates without a cap (used by Custom Analysis)
- `tests/test_ticker_utils.py`: 25 tests covering parse and validate; `tests/test_scoring.py`: 3 tests for the new `top_n` parameter

### Fixed — Finnhub thread-safe throttle and 403 retry
- `src/alphavision/providers/analyst.py`: added `threading.Lock` (`_throttle_lock`) around `_throttle()` — without it, all three parallel fetch workers read the same `_last_call_at` simultaneously, bypass the sleep, and burst Finnhub within milliseconds; Finnhub returns HTTP 403 for the concurrent overflow
- `src/alphavision/providers/analyst.py`: HTTP 403 is now treated identically to 429 (exponential backoff retry up to `_FINNHUB_MAX_RETRIES`) — Finnhub uses 403 for per-second burst violations in addition to 429 for per-minute rate limits; after retries are exhausted the yfinance fallback activates
- `tests/test_providers_analyst.py`: added `test_403_then_200_retries` and `test_403_persistent_returns_none`; added `test_lock_prevents_concurrent_bypass`

### Added — provider fallback chains, enhanced logging, pre-flight UI check
- `src/alphavision/providers/analyst.py`: `_analyst_from_yfinance()` — yfinance fallback for `net_upgrades_30d`, `analyst_count`, `strong_buy_count`, `buy_count`, and `target_mean_price` when `FINNHUB_API_KEY` is absent or Finnhub returns empty data
- `src/alphavision/providers/fundamentals.py`: `_yfinance_fundamentals_snapshot()` — yfinance `info` dict fallback for `rule_of_40` and `earnings_quality` when EDGAR finds no filing or XBRL parses to null metrics
- `src/alphavision/data_fetcher.py`: `ProviderStatus` dataclass and `probe_providers()` — env-var-based pre-flight check surfacing which providers are configured; no network I/O
- `.env.template`: committed environment variable template with inline documentation for `FINNHUB_API_KEY`, `EDGAR_IDENTITY`, and `AZURE_STORAGE_CONNECTION_STRING`
- `docs/providers.md`: full rewrite — fallback chains, console log format, signal degradation tables, pre-flight probe API, yfinance fallback field mapping

### Changed — provider fallback chains, enhanced logging, pre-flight UI check
- `src/alphavision/providers/prices.py`: added `INFO` log per ticker: `prices  | TICKER | yfinance history()`
- `src/alphavision/providers/analyst.py`: `fetch_analyst_snapshot` now logs which platform is used (`Finnhub API` / `no Finnhub key → yfinance fallback` / `Finnhub empty → yfinance fallback`) at `INFO` level; structured log format `analyst | TICKER | <source>`
- `src/alphavision/providers/fundamentals.py`: `fetch_fundamentals_snapshot` now logs `fundams | TICKER | SEC EDGAR (XBRL)` and `EDGAR no filing → yfinance fallback` / `EDGAR empty metrics → yfinance fallback`; activates yfinance fallback when EDGAR returns null metrics
- `src/alphavision/data_fetcher.py`: `fetch_ticker` logs `fetch   | TICKER | starting` at `INFO` level; `probe_providers()` import from analyst module uses module-level constant
- `app.py`: replaced single-phase button with 5-phase state machine — preflight → confirm (provider status panel with Continue/Cancel) → running → done; provider source shown in results caption; "Run New Analysis" button to restart
- `tests/test_providers_analyst.py`: updated `test_subcall_exception_yields_default` and `test_all_failures_yield_neutral` to patch `_analyst_from_yfinance`; added `TestAnalystFromYfinance` (5 tests) and `TestFetchAnalystSnapshotFallback` (3 tests)
- `tests/test_providers_fundamentals.py`: updated `test_no_filing_returns_neutral` and `test_xbrl_exception_yields_empty_facts` to patch `_yfinance_fundamentals_snapshot`; added `TestYfinanceFundamentalsSnapshot` (5 tests) and `TestFetchFundamentalsSnapshotFallback` (2 tests)
- `tests/test_data_fetcher.py`: added `TestProbeProviders` (5 tests)

### Added — v3.0 provider bundle (Finnhub + SEC EDGAR)
- `src/alphavision/providers/` package: three independent data providers — `prices.py` (yfinance history), `analyst.py` (Finnhub REST + yfinance EPS trend), `fundamentals.py` (SEC EDGAR XBRL via edgartools, SQLite-cached)
- `TickerData`: `net_upgrades_30d` (Finnhub upgrade/downgrade net count, last 30 days), `eps_revision_slope` (mean fractional EPS revision slope across 7d/30d/60d/90d windows), `earnings_quality` (FCF / Net Income)
- `ScoredTicker`: `earnings_quality` passthrough field
- `docs/providers.md`: new doc covering all three providers, rate limits, and fallback behaviour
- `.env.example`: `FINNHUB_API_KEY` and `EDGAR_IDENTITY` entries
- `tests/test_providers_prices.py`, `tests/test_providers_analyst.py`, `tests/test_providers_fundamentals.py`: 96 new tests covering all three providers

### Changed — v3.0 provider bundle
- `src/alphavision/data_fetcher.py`: rewritten as thin orchestrator; `fetch_ticker` now calls three independent providers; graceful degradation — analyst/fundamentals failures yield neutral defaults without dropping the row
- `src/alphavision/scoring.py`: Rating Drift formula updated to `clamp(50 + net_upgrades_30d × 10)` (previously Strong-Buy fraction); EPS Revision uses `eps_revision_slope` (slope, not a single point)
- `docs/data_fetcher.md`: rewritten to reflect three-provider architecture
- `docs/scoring.md`: Rating Drift and EPS Revision sub-score definitions updated; `earnings_quality` added to `ScoredTicker` model table; `_RATING_DRIFT_PER_NET_UPGRADE` constant added
- `pyproject.toml`: added `requests`, `edgartools`, `python-dotenv`; added mypy overrides for `edgar` and `edgar.*`
- `tests/test_data_fetcher.py`, `tests/test_scoring.py`, `tests/test_filters.py`: updated for new field names and provider architecture; 233 tests pass, 93% coverage

### Added — v3.0 Forward-Momentum methodology pivot
- `docs/METADOLOGY.md`: rewritten to v3.0 — single Forward-Momentum gate (price > SMA-200, return_12_1 > 0, price ≤ 1.15 × SMA-20, ≥ 3 analysts) and six-factor Conviction Score weighted toward forward signals: Relative Strength (12-1) 30%, EPS Revision 25%, Rating Drift 15%, Trend Quality 15%, Upside Gap 10%, Consensus 5%
- `src/alphavision/scoring.py`: `_trend_quality_score`, `_extension_pct`, and a stress-test penalty that dampens conviction by 10% when price > 1.10 × SMA-20
- `src/alphavision/data_fetcher.py`: `_compute_return_12_1` (Jegadeesh-Titman 12-1 window) and `_fetch_benchmark_return_12_1` (uses SPY price history directly, bypassing the `Ticker.info` 404 that silently zeroed RS in v2.0)
- `src/alphavision/models.py`: `TickerData.sma_20`, `TickerData.return_12_1`, `TickerData.relative_strength_12_1`; `ScoredTicker.trend_quality_score`, `ScoredTicker.eps_revision_score`, `ScoredTicker.extension_pct`, `ScoredTicker.over_extended`
- `docs/archive/METADOLOGY_v2.md`: archived v2.0 methodology for historical reference

### Changed — v3.0 Forward-Momentum methodology pivot
- `src/alphavision/filters.py`: `apply_dual_track` / `passes_turnaround` / `passes_momentum` replaced by `apply_forward_momentum` / `passes_forward_momentum`; Channel A (Turnaround) removed because its mean-reversion bias produced a v2.0 Top 20 that was 20-of-20 Fallen Angels
- `src/alphavision/scoring.py`: `WEIGHTS` updated to v3.0 (relative_strength 0.30, eps_revision 0.25, rating_drift 0.15, trend_quality 0.15, upside_gap 0.10, consensus_strength 0.05); `_UPSIDE_CAP` tightened from 0.50 → 0.30; Channel A RS bypass removed
- `src/alphavision/models.py`: removed `price_6m_high`, `drawdown_pct`, `return_6m`, `relative_strength_6m`, and `ScoredTicker.channel` (no longer used after the v3.0 pivot)
- `src/alphavision/data_fetcher.py`: `fetch_ticker` now computes `sma_20`, `sma_200`, and `return_12_1`; no longer computes `price_6m_high`, `drawdown_pct`, `return_6m`
- `app.py`: Top 20 table reorganised for v3.0 sub-scores; added Extension % and Stretched flag columns; Channel column removed
- `tests/`: `test_filters.py`, `test_scoring.py`, `test_data_fetcher.py` rewritten for v3.0; 186 tests pass with 99% coverage

### Added
- `src/alphavision/data_fetcher.py`: `_fetch_benchmark_return()` — fetches SPY 6-month return as the market benchmark for relative strength computation
- `src/alphavision/data_fetcher.py`: `_extract_rule_of_40()` — computes Rule of 40 (revenue growth % + FCF margin %) from yfinance `info` dict
- `src/alphavision/scoring.py`: `_relative_strength_score()` — fifth conviction factor (15%); Channel A-only stocks receive neutral 50 to avoid double-penalizing drawdown candidates
- `docs/archive/METADOLOGY_v1.md`: archived original v1 methodology for historical reference

### Changed
- `docs/METADOLOGY.md`: upgraded to v2.0 — five-factor Conviction Score (Upside Gap 35%, Rating Drift 25%, Relative Strength 15%, Consensus 15%, EPS Momentum 10%); Rule of 40 quality signal documented; all Turkish text replaced with English
- `src/alphavision/models.py`: `TickerData` — added `relative_strength_6m: float = 0.0` and `rule_of_40: float | None = None`; `ScoredTicker` — added `relative_strength_score: float` and `rule_of_40: float | None`
- `src/alphavision/scoring.py`: `WEIGHTS` updated to v2 (upside_gap 0.35, rating_drift 0.25, relative_strength 0.15, consensus_strength 0.15, eps_momentum 0.10); `compute_conviction_score` now computes five sub-scores
- `src/alphavision/data_fetcher.py`: `fetch_ticker` fetches `revenueGrowth`, `freeCashflow`, `totalRevenue` to compute `rule_of_40`; `fetch_universe` calls `_fetch_benchmark_return()` and populates `relative_strength_6m` for every result
- `app.py`: Top 20 table shows Rel. Strength and Rule of 40 columns; scoring description updated to v2.0 weights
- `docs/scoring.md`: updated formula, weight table, sub-score definitions, and `ScoredTicker` model for v2.0
- `docs/data_fetcher.md`: documented `relative_strength_6m`, `rule_of_40`, `_fetch_benchmark_return`, and new yfinance data sources
- `src/alphavision/data_fetcher.py`: `fetch_universe` now fetches tickers in parallel via `ThreadPoolExecutor` (default 5 workers), reducing wall-clock time for ~520 tickers by ~5×; input order is preserved
- `src/alphavision/data_fetcher.py`: replace per-ticker retry with batch retry loop — rate-limited tickers are retried as a group after a growing cooldown (8 s × round), guaranteeing all tickers are fetched; default workers reduced to 3 to lower rate-limit pressure
- `app.py`: Analysis tab replaced sequential per-ticker loop with parallel `fetch_universe` call inside `st.spinner`

### Removed
- `docs/METADOLOGY_v2.md`: draft file superseded by the promoted v2.0 methodology now in `docs/METADOLOGY.md`

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
