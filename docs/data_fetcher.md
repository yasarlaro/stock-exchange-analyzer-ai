# Data Fetcher

**Purpose**: Thin orchestrator that composes a `TickerData` from three
independent data providers (prices, analyst, fundamentals) and runs the
multi-round batch-retry universe fetch.

See [docs/providers.md](providers.md) for the per-provider details.

## Public API

### `fetch_ticker(ticker: str) -> TickerData`

Fetches one ticker by calling all three providers in sequence.

1. **Prices** (`fetch_price_snapshot`) — runs first; the only call that
   may raise. A missing or too-short price history makes the ticker
   unscoreable; the error propagates.
2. **Analyst** (`fetch_analyst_snapshot`) — failures log a warning and
   return an `AnalystSnapshot` with neutral defaults so the row is kept.
3. **Fundamentals** (`fetch_fundamentals_snapshot`) — same graceful
   degradation; `rule_of_40` and `earnings_quality` become `None`.

`relative_strength_12_1` is always `0.0` here; populated by
`fetch_universe()` after the SPY benchmark is fetched.

**Args**: `ticker` — stock ticker symbol (e.g. `"AAPL"`).

**Returns**: `TickerData` with all fields populated (analyst / fundamentals
fields default to `0` / `None` on provider failure).

**Raises**: `ValueError` — if price history is missing or too short (< 2 rows).

**Example**:
```python
from alphavision.data_fetcher import fetch_ticker

data = fetch_ticker("AAPL")
print(data.current_price, data.return_12_1, data.rule_of_40)
```

---

### `fetch_universe(tickers: list[str], max_workers: int = 3) -> list[TickerData]`

Fetches all tickers in parallel, retrying rate-limited ones until none
remain or `_MAX_RETRY_ROUNDS` is exhausted.

After the batch, SPY is fetched once as the market benchmark.
`relative_strength_12_1 = return_12_1 − spy_return_12_1` for every
result. Falls back to `0.0` benchmark when SPY is unavailable.

**Args**:
- `tickers` — list of ticker symbols.
- `max_workers` — concurrent fetch threads per round (default `3`).

**Returns**: `list[TickerData]` in input order with
`relative_strength_12_1` populated.

**Configuration constants** (module-level):

| Constant | Default | Purpose |
|---|---|---|
| `_DEFAULT_MAX_WORKERS` | `3` | Concurrent threads per round |
| `_RATE_LIMIT_COOLDOWN` | `8.0` s | Base sleep between retry rounds |
| `_MAX_RETRY_ROUNDS` | `10` | Safety cap on retry loop |
| `_BENCHMARK_TICKER` | `"SPY"` | Market benchmark for RS computation |

---

## Models

### `TickerData` (from `alphavision.models`)

| Field | Type | Description |
|---|---|---|
| `ticker` | `str` | Ticker symbol |
| `company` | `str` | Company long name |
| `current_price` | `float` | Most recent closing price |
| `sma_20` | `float` | 20-day simple moving average |
| `sma_200` | `float` | 200-day simple moving average |
| `return_12_1` | `float` | 12-1 month return (Jegadeesh-Titman) |
| `relative_strength_12_1` | `float` | `return_12_1 − spy_return_12_1`; `0.0` from `fetch_ticker` |
| `target_mean_price` | `float \| None` | Analyst mean price target |
| `analyst_count` | `int` | Analysts in latest recommendation snapshot |
| `strong_buy_count` | `int` | Strong Buy ratings |
| `buy_count` | `int` | Buy ratings |
| `net_upgrades_30d` | `int` | Upgrades − downgrades in last 30 days |
| `eps_revision_slope` | `float` | Mean fractional EPS revision slope |
| `rule_of_40` | `float \| None` | Revenue growth % + FCF margin % |
| `earnings_quality` | `float \| None` | FCF / Net Income ratio |

---

## Data Sources

| Metric | Provider | Source |
|---|---|---|
| Price history, SMAs, 12-1 | `prices.py` | `yf.Ticker.history()` |
| Benchmark (SPY) | `prices.py` | `yf.Ticker("SPY").history()` (price-only) |
| Net upgrades 30d | `analyst.py` | Finnhub `/stock/upgrade-downgrade` |
| Analyst consensus | `analyst.py` | Finnhub `/stock/recommendation` |
| Price target | `analyst.py` | Finnhub `/stock/price-target` |
| EPS revision slope | `analyst.py` | `yf.Ticker.get_eps_trend()` |
| Rule of 40, Earnings Quality | `fundamentals.py` | SEC EDGAR XBRL via edgartools |
