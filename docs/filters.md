# Filters

**Purpose**: Forward-Momentum gate (v3.0) — admits tickers in confirmed
uptrends with positive intermediate-horizon momentum, sufficient
analyst coverage, and which are not climactically over-extended.

## Public API

### `passes_forward_momentum(data: TickerData) -> bool`

Returns `True` iff the ticker passes **all four** gates:

1. `current_price > sma_200` — long-term trend up.
2. `return_12_1 > 0` — positive Jegadeesh-Titman 12-1 momentum.
3. `current_price ≤ 1.15 × sma_20` — not over-extended above the 20-day SMA.
4. `analyst_count ≥ 3` — minimum coverage so analyst sub-scores are
   statistically meaningful.

Returns `False` if `sma_20` or `sma_200` is non-positive (defensive).

---

### `apply_forward_momentum(universe: list[TickerData]) -> list[TickerData]`

Apply the gate; return the subset of tickers that pass.

**Args**: `universe` — full list of `TickerData` from `fetch_universe()`.

**Returns**: Filtered subset in input order.

**Example**:
```python
from alphavision.data_fetcher import fetch_universe
from alphavision.filters import apply_forward_momentum
from alphavision.universe import build_universe

tickers = build_universe()["ticker"].tolist()
universe_data = fetch_universe(tickers)
candidates = apply_forward_momentum(universe_data)
print(f"{len(candidates)} candidates from {len(universe_data)} tickers")
```

---

## Constants

| Constant | Value | Gate |
|---|---|---|
| `SMA_200_MULTIPLIER` | `1.0` | Gate 1 — `price > 1.0 × sma_200` |
| `RETURN_12_1_THRESHOLD` | `0.0` | Gate 2 — `return_12_1 > 0` |
| `EXTENSION_CAP` | `1.15` | Gate 3 — `price ≤ 1.15 × sma_20` |
| `MIN_ANALYST_COUNT` | `3` | Gate 4 — `analyst_count ≥ 3` |

## What changed from v2.0

- Channel A (Turnaround) **removed** — Mean-reversion bias on a
  forward-momentum mandate.
- Channel B (Momentum) replaced with the four-gate Forward-Momentum
  filter; `return_6m` swapped for the 12-1 window, plus an
  over-extension cap and analyst-count floor.
- `ScoredTicker.channel` is no longer populated; reviewers can use
  `ScoredTicker.over_extended` and `ScoredTicker.extension_pct` for
  diagnostics.
