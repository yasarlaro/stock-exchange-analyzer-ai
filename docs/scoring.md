# Scoring

**Purpose**: Conviction Score engine — scores every filtered candidate on four factors and returns the Top 20 ranked list.

## Public API

### `compute_conviction_score(data: TickerData) -> ScoredTicker`

Compute all four sub-scores and the weighted Conviction Score for a single ticker.

**Args**: `data` — `TickerData` from `fetch_ticker()` / `fetch_universe()`

**Returns**: `ScoredTicker` with all scores in [0, 100] and `rank=0`.
Rank is assigned by `rank_candidates()`.

---

### `rank_candidates(candidates: list[TickerData]) -> list[ScoredTicker]`

Score all candidates and return the Top 20, ranked descending.

**Args**: `candidates` — output of `apply_dual_track()`

**Returns**: Up to 20 `ScoredTicker` instances, `rank=1` = highest conviction.

**Example**:
```python
from alphavision.filters import apply_dual_track
from alphavision.scoring import rank_candidates

candidates = apply_dual_track(universe_data)
top20 = rank_candidates(candidates)
for s in top20:
    print(f"{s.rank:2d}. {s.ticker:<6} {s.conviction_score:.1f}  [{s.channel}]")
```

---

## Conviction Score Formula

```
conviction_score = 0.40 × upside_gap
                 + 0.30 × rating_drift
                 + 0.20 × consensus_strength
                 + 0.10 × eps_momentum
```

All sub-scores are in **[0, 100]**; the total is also in [0, 100].

### Sub-score Definitions

| Sub-score | Weight | Formula | Source Field |
|---|---|---|---|
| Upside Gap | 40% | `clamp(0, (target/current − 1) / 0.50 × 100, 100)` | `target_mean_price`, `current_price` |
| Rating Drift | 30% | `clamp(0, strong_buy / analyst_count × 100, 100)` | `strong_buy_count`, `analyst_count` |
| Consensus Strength | 20% | `clamp(0, (strong_buy + buy) / analyst_count × 100, 100)` | `strong_buy_count`, `buy_count`, `analyst_count` |
| EPS Momentum | 10% | `clamp(0, 50 + revision × 500, 100)` | `eps_revision_direction` |

### Normalization Constants

| Constant | Value | Meaning |
|---|---|---|
| `_UPSIDE_CAP` | `0.50` | 50% analyst upside → sub-score 100 |
| `_EPS_SCALE` | `500.0` | ±10% EPS revision → sub-score swing of ±50 pts |

---

## `ScoredTicker` Model

| Field | Type | Description |
|---|---|---|
| `ticker` | `str` | Ticker symbol |
| `company` | `str` | Company long name |
| `conviction_score` | `float` | Weighted total, rounded to 2 d.p. |
| `upside_gap_score` | `float` | Upside Gap sub-score [0, 100] |
| `rating_drift_score` | `float` | Rating Drift sub-score [0, 100] |
| `consensus_strength_score` | `float` | Consensus Strength sub-score [0, 100] |
| `eps_momentum_score` | `float` | EPS Momentum sub-score [0, 100] |
| `rank` | `int` | 1–20; 0 before `rank_candidates()` assigns it |
| `channel` | `str` | `'A'`, `'B'`, or `'BOTH'` |

---

## Weights Constant

```python
WEIGHTS: dict[str, float] = {
    "upside_gap":         0.40,
    "rating_drift":       0.30,
    "consensus_strength": 0.20,
    "eps_momentum":       0.10,
}
```

The weights sum to exactly 1.0.

## Key Decisions

- **Rating Drift proxy**: uses the Strong Buy fraction (not raw EPS) to provide a distinct signal from EPS Momentum; temporal rating-change data (e.g. upgrades/downgrades vs. prior period) will be added in a future data-fetcher enhancement.
- **Top N = 20**: matches the Leadership Board's weekly reporting granularity.
- **Deterministic**: same inputs always produce the same output; no randomness.
