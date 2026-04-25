# Data Fetcher

**Purpose**: yfinance wrapper that fetches per-ticker price history and analyst metrics needed by the filtering and scoring engines.

## Public API

### `fetch_ticker(ticker: str) -> TickerData`

Fetches 1-year price history and analyst consensus data for a single ticker.

**Args**: `ticker` — stock ticker symbol (e.g., `"AAPL"`)

**Returns**: `TickerData` with all price and analyst fields populated.

**Raises**: `ValueError` — if price history is missing or too short to compute metrics.

**Example**:
```python
from alphavision.data_fetcher import fetch_ticker

data = fetch_ticker("AAPL")
print(data.current_price, data.drawdown_pct, data.analyst_count)
```

---

### `fetch_universe(tickers: list[str]) -> list[TickerData]`

Fetches data for every ticker in the list. Tickers that raise any exception are silently skipped (a warning is logged).

**Args**: `tickers` — list of ticker symbols (e.g., from `build_universe()`)

**Returns**: List of `TickerData`; length ≤ `len(tickers)`.

**Example**:
```python
from alphavision.data_fetcher import fetch_universe
from alphavision.universe import build_universe

tickers = build_universe()["ticker"].tolist()
universe_data = fetch_universe(tickers)
```

---

## Models

### `TickerData` (from `alphavision.models`)

| Field | Type | Description |
|---|---|---|
| `ticker` | `str` | Ticker symbol |
| `current_price` | `float` | Most recent closing price |
| `price_6m_high` | `float` | Max closing price in last ~126 trading days |
| `drawdown_pct` | `float` | `(current - 6m_high) / 6m_high`; ≤ 0 |
| `sma_200` | `float` | 200-day simple moving average of close |
| `return_6m` | `float` | `(current - 6m_ago) / 6m_ago` |
| `target_mean_price` | `float \| None` | Analyst mean price target; None if unavailable |
| `analyst_count` | `int` | Number of analysts covering the ticker |
| `strong_buy_count` | `int` | Strong Buy ratings (current period) |
| `buy_count` | `int` | Buy ratings (current period) |
| `eps_revision_direction` | `float` | Positive = upward EPS revisions (30-day comparison) |

---

## Data Sources

| Metric | yfinance Source |
|---|---|
| Price history | `Ticker.history(period="1y")["Close"]` |
| Analyst target | `Ticker.info["targetMeanPrice"]` |
| Analyst count | `Ticker.info["numberOfAnalystOpinions"]` |
| Rating counts | `Ticker.recommendations_summary` (period `"0m"`) |
| EPS revision | `Ticker.get_eps_trend()` (current vs. 30daysAgo) |

---

## Configuration

No environment variables required. All data is fetched via yfinance's
free, unauthenticated API.

## Notes

- `_TRADING_DAYS_6M = 126`: approximately 6 calendar months of trading days.
- `_TRADING_DAYS_200 = 200`: SMA-200 window; falls back to all available days if history is shorter.
- All analyst fields default to `0` / `None` when yfinance returns no data — the function never raises for missing analyst data.
