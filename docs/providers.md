# Providers

**Package**: `alphavision.providers`

Three independent modules, each responsible for one data source. Each
exposes a typed snapshot dataclass and a `fetch_*` entry point. Failures
are isolated: a broken provider returns neutral defaults rather than
dropping the row.

---

## Configuration — Required Environment Variables

Create a `.env` file from `.env.template` at the project root. The
application uses `python-dotenv` to load it automatically at startup.

| Variable | Required for | Without it |
|---|---|---|
| `FINNHUB_API_KEY` | Analyst ratings, upgrades/downgrades, price targets | Falls back to yfinance analyst data (reduced accuracy — see below) |
| `EDGAR_IDENTITY` | SEC EDGAR XBRL filings (Rule of 40, Earnings Quality) | Uses generic SEC identity; SEC rate limits may be tighter |

**Free-tier limits**

| Provider | Free limit | Notes |
|---|---|---|
| Finnhub | 60 calls / minute | Built-in throttle in `analyst.py` (1.05 s between calls) |
| SEC EDGAR | 10 requests / second (Fair Access) | edgartools adds its own throttle |
| yfinance | ~1–2 req/s burst (no hard limit) | ThreadPoolExecutor limited to 3 workers |

---

## prices.py — yfinance price history

**Entry point**: `fetch_price_snapshot(ticker: str) -> PriceSnapshot`

Fetches 1-year `Ticker.history()` and computes:
- `current_price` — last closing price
- `sma_20`, `sma_200` — trailing moving averages
- `return_12_1` — Jegadeesh-Titman 12-1 month return

**Raises** `ValueError` when history is missing or shorter than 2 rows.
Price failure is the only one that propagates — it makes the ticker
unscoreable.

**Console log format**

```
INFO alphavision.providers.prices: prices  | AAPL   | yfinance history()
```

**`fetch_benchmark_return_12_1(ticker: str = "SPY") -> float`**

Fetches SPY return via `Ticker.history()` only, bypassing `.info` (which
returns 404 for ETFs). Returns `0.0` on any error.

**`compute_return_12_1(closes: pd.Series) -> float`**

```
price_12m_ago = closes.iloc[-252]   # earliest available if shorter
price_1m_ago  = closes.iloc[-21]
return_12_1   = price_1m_ago / price_12m_ago − 1
```

Returns `0.0` for single-row series or zero anchor.

**`is_rate_limited(exc: Exception) -> bool`**

Returns `True` when the exception message contains `"Too Many Requests"`
or `"Rate limited"` — used by `fetch_universe` to decide whether to
retry or skip.

---

## analyst.py — Finnhub (primary) / yfinance (fallback)

**Entry point**: `fetch_analyst_snapshot(ticker: str) -> AnalystSnapshot`

### Fallback chain

| Priority | Source | Activated when |
|---|---|---|
| 1 (primary) | Finnhub API | `FINNHUB_API_KEY` is set in environment |
| 2 (fallback) | yfinance (`recommendations_summary`, `analyst_price_targets`, `upgrades_downgrades`) | Finnhub key is absent, or Finnhub returns all-zero/null data for the ticker |

**Console log format**

```
# Finnhub primary
INFO alphavision.providers.analyst: analyst | AAPL   | Finnhub API

# Fallback — no key
INFO alphavision.providers.analyst: analyst | AAPL   | no Finnhub key → yfinance fallback

# Fallback — Finnhub returned nothing useful
INFO alphavision.providers.analyst: analyst | AAPL   | Finnhub empty → yfinance fallback
```

**What degrades without `FINNHUB_API_KEY`**

| Field | Finnhub source | yfinance fallback | Impact on score |
|---|---|---|---|
| `net_upgrades_30d` | Individual event timestamps (`/stock/upgrade-downgrade`) | `upgrades_downgrades` DataFrame (also event-based) | Minimal — same concept |
| `analyst_count` | Recommendation snapshot total | `recommendations_summary` monthly count | Minimal |
| `strong_buy_count` / `buy_count` | Recommendation snapshot | `recommendations_summary` | Minimal |
| `target_mean_price` | `/stock/price-target` | `analyst_price_targets["mean"]` | Upside Gap score affected |

**EPS revision slope** always uses yfinance `get_eps_trend()` regardless
of Finnhub availability — there is no equivalent free Finnhub endpoint.

**Rate limiting**

Built-in 1.05-second minimum interval between Finnhub calls. 429 responses
trigger exponential backoff (2 s, 4 s, 8 s) with up to 3 retries before
returning `None` and proceeding with defaults.

---

## fundamentals.py — SEC EDGAR XBRL (primary) / yfinance (fallback)

**Entry point**: `fetch_fundamentals_snapshot(ticker: str) -> FundamentalsSnapshot`

### Fallback chain

| Priority | Source | Activated when |
|---|---|---|
| 1 (primary) | SEC EDGAR XBRL via edgartools | Always attempted (default identity used if `EDGAR_IDENTITY` not set) |
| 2 (fallback) | yfinance `Ticker.info` | EDGAR finds no filing, or EDGAR XBRL parses to all-null metrics |

**Console log format**

```
# EDGAR primary
INFO alphavision.providers.fundamentals: fundams | AAPL   | SEC EDGAR (XBRL)
INFO alphavision.providers.fundamentals: fundams | AAPL   | EDGAR cache hit (0001193125-24-087654)

# Fallbacks
INFO alphavision.providers.fundamentals: fundams | AAPL   | EDGAR no filing → yfinance fallback
INFO alphavision.providers.fundamentals: fundams | AAPL   | EDGAR empty metrics → yfinance fallback
```

**EDGAR identity**

Set `EDGAR_IDENTITY` to a real name and email address as required by the
SEC Fair Access policy. The default identity
(`AlphaVision Research research@alphavision.local`) still works but may
experience tighter rate limiting.

**SQLite cache**

Stored at `data/fundamentals_cache.db`, keyed by `(ticker, accession_number)`.
Filings are immutable once published — a cache hit means the XBRL is
never re-fetched for the same statement. The cache survives across weekly
runs; delete it only to force a full refresh.

**Computed metrics**

| Metric | Formula | Tags tried (in order) |
|---|---|---|
| `rule_of_40` | `revenue_growth_yoy% + fcf_margin%` | Revenue: `Revenues`, `RevenueFromContractWithCustomer*`, `SalesRevenueNet` |
| `earnings_quality` | `FCF / NetIncome` | NetIncome: `NetIncomeLoss`, `ProfitLoss` |

FCF = Operating Cash Flow − |CapEx|

**yfinance fallback mapping**

| Field | yfinance info key | Note |
|---|---|---|
| Revenue growth | `revenueGrowth` | Fractional (0.15 = 15%) |
| FCF | `freeCashflow` | Absolute value (USD) |
| Total revenue | `totalRevenue` | Used as FCF margin denominator |
| Net income | `netIncomeToCommon` | Used for earnings quality |

Coverage ~70–75% of the universe (vs. ~95% for EDGAR).

---

## Pre-flight check — `probe_providers()`

**Location**: `alphavision.data_fetcher.probe_providers()`

Called by `app.py` before running the full universe fetch. Reads
environment variables (no network I/O) and returns a `ProviderStatus`
dataclass with:

- `prices_source` — always `"yfinance"`
- `analyst_source` — `"finnhub"` when `FINNHUB_API_KEY` is set, else `"yfinance"`
- `fundamentals_source` — always `"edgar"`
- `finnhub_key_set` — `True` iff key is in environment
- `edgar_identity_custom` — `True` iff `EDGAR_IDENTITY` is explicitly set
- `warnings` — list of human-readable degradation notices

The Streamlit UI shows this status in a provider panel and requires the
user to click **Continue** before the expensive analysis begins.

---

## Full console log example (single ticker)

```
INFO alphavision.data_fetcher:    fetch   | AAPL   | starting
INFO alphavision.providers.prices: prices  | AAPL   | yfinance history()
INFO alphavision.providers.analyst: analyst | AAPL   | no Finnhub key → yfinance fallback
INFO alphavision.providers.fundamentals: fundams | AAPL   | SEC EDGAR (XBRL)
INFO alphavision.providers.fundamentals: fundams | AAPL   | EDGAR no filing → yfinance fallback
```
