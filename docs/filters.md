# Filters

**Purpose**: Dual-Track filtering engine — classifies each ticker into Channel A (Turnaround), Channel B (Momentum), or excludes it from scoring.

## Public API

### `passes_turnaround(data: TickerData) -> bool`

Channel A gate: stock has declined ≥25% from its 6-month peak.

**Returns**: `True` if `data.drawdown_pct <= TURNAROUND_DRAWDOWN_THRESHOLD (-0.25)`.

---

### `passes_momentum(data: TickerData) -> bool`

Channel B gate: price above SMA-200 AND positive 6-month return.

**Returns**: `True` if `current_price > sma_200 × MOMENTUM_SMA_MULTIPLIER`
AND `return_6m > MOMENTUM_RETURN_THRESHOLD (0.0)`.

---

### `apply_dual_track(universe: list[TickerData]) -> list[TickerData]`

Apply both channels; return tickers that pass at least one.

**Args**: `universe` — full list of `TickerData` from `fetch_universe()`

**Returns**: Filtered subset; tickers qualifying for both channels appear once. Input order preserved.

**Example**:
```python
from alphavision.data_fetcher import fetch_universe
from alphavision.filters import apply_dual_track
from alphavision.universe import build_universe

tickers = build_universe()["ticker"].tolist()
universe_data = fetch_universe(tickers)
candidates = apply_dual_track(universe_data)
print(f"{len(candidates)} candidates from {len(universe_data)} tickers")
```

---

## Constants

| Constant | Value | Description |
|---|---|---|
| `TURNAROUND_DRAWDOWN_THRESHOLD` | `-0.25` | Channel A: drawdown must be ≤ -25% |
| `MOMENTUM_SMA_MULTIPLIER` | `1.0` | Channel B: price must exceed 1× SMA-200 |
| `MOMENTUM_RETURN_THRESHOLD` | `0.0` | Channel B: 6m return must be strictly positive |

## Channel Assignment

| Scenario | Channel |
|---|---|
| Only passes turnaround | A |
| Only passes momentum | B |
| Passes both | BOTH (included once) |
| Passes neither | Excluded |

The channel field is stored in `ScoredTicker.channel` after scoring (see [scoring.md](scoring.md)).
