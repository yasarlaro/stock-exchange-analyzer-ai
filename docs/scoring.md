# Scoring

**Purpose**: Forward-Momentum Conviction Score engine (v3.0) — scores
every gate-survivor on six factors and returns the Top 20 ranked list.

## Public API

### `compute_conviction_score(data: TickerData) -> ScoredTicker`

Compute the six sub-scores, the weighted total, and the over-extension
penalty for a single ticker.

**Args**: `data` — `TickerData` from `fetch_ticker()` /
`fetch_universe()`.

**Returns**: `ScoredTicker` with all sub-scores in `[0, 100]`,
`extension_pct`, `over_extended`, and `rank=0`. Rank is assigned by
`rank_candidates()`.

---

### `rank_candidates(candidates: list[TickerData]) -> list[ScoredTicker]`

Score all candidates and return the Top 20, ranked descending.

**Args**: `candidates` — output of `apply_forward_momentum()`.

**Returns**: Up to 20 `ScoredTicker` instances; `rank=1` = highest.

**Example**:
```python
from alphavision.filters import apply_forward_momentum
from alphavision.scoring import rank_candidates

candidates = apply_forward_momentum(universe_data)
top20 = rank_candidates(candidates)
for s in top20:
    print(
        f"{s.rank:2d}. {s.ticker:<6} {s.conviction_score:.1f}"
        f"  RS={s.relative_strength_score:.1f}"
        f"  EPS={s.eps_revision_score:.1f}"
        f"  ext={s.extension_pct:+.2%}"
    )
```

---

## Conviction Score Formula (v3.0)

```
raw_total = 0.30 × relative_strength
          + 0.25 × eps_revision
          + 0.15 × rating_drift
          + 0.15 × trend_quality
          + 0.10 × upside_gap
          + 0.05 × consensus_strength

if extension_pct > 0.10:
    conviction_score = raw_total × 0.90
else:
    conviction_score = raw_total
```

All sub-scores are in **`[0, 100]`**; the total is also in `[0, 100]`.

### Sub-score Definitions

| Sub-score | Weight | Formula | Source Field |
|---|---|---|---|
| Relative Strength (12-1) | 30% | `clamp(50 + rs_12_1 × 200)` | `relative_strength_12_1` |
| EPS Revision | 25% | `clamp(50 + slope × 500)` | `eps_revision_slope` |
| Rating Drift | 15% | `clamp(50 + net_upgrades_30d × 10)` | `net_upgrades_30d` |
| Trend Quality | 15% | `clamp(50 + (price/sma_200 − 1) × 200)` | `current_price`, `sma_200` |
| Upside Gap | 10% | `clamp((target/price − 1) / 0.30 × 100)` | `target_mean_price`, `current_price` |
| Consensus | 5% | `clamp((strong_buy + buy) / analyst_count × 100)` | `strong_buy_count`, `buy_count`, `analyst_count` |

### Stress-Test Penalty

Tickers stretched more than **10%** above their 20-day SMA have their
final score multiplied by **0.90**. The entry gate already excludes
anything stretched **>15%** above the 20-day SMA, so the penalty band
is narrow but explicitly discourages chasing names within the
candidate pool that are still extended.

`extension_pct` and `over_extended` are persisted on every
`ScoredTicker` for transparency.

### Normalisation Constants

| Constant | Value | Meaning |
|---|---|---|
| `_RS_SCALE` | `200.0` | ±25% RS → ±50 sub-score swing |
| `_EPS_SCALE` | `500.0` | ±10% EPS revision slope → ±50 sub-score swing |
| `_TREND_SCALE` | `200.0` | +25% above SMA-200 → +50 sub-score swing |
| `_UPSIDE_CAP` | `0.30` | 30% analyst upside → sub-score 100 |
| `_RATING_DRIFT_PER_NET_UPGRADE` | `10.0` | Points added per net upgrade; 5 upgrades → 100 |
| `_EXTENSION_PENALTY_THRESHOLD` | `0.10` | Trigger band for stress-test |
| `_EXTENSION_PENALTY_FACTOR` | `0.90` | Multiplier when stretched |

---

## `ScoredTicker` Model

| Field | Type | Description |
|---|---|---|
| `ticker` | `str` | Ticker symbol |
| `company` | `str` | Company long name |
| `conviction_score` | `float` | Weighted total after over-extension penalty |
| `relative_strength_score` | `float` | RS (12-1) sub-score `[0, 100]` |
| `eps_revision_score` | `float` | EPS revision sub-score `[0, 100]` |
| `rating_drift_score` | `float` | Net-upgrades sub-score `[0, 100]` |
| `trend_quality_score` | `float` | Price-vs-SMA200 sub-score `[0, 100]` |
| `upside_gap_score` | `float` | Upside Gap sub-score `[0, 100]` |
| `consensus_strength_score` | `float` | Buy + Strong-Buy fraction sub-score `[0, 100]` |
| `extension_pct` | `float` | `current_price / sma_20 − 1` |
| `over_extended` | `bool` | True iff `extension_pct > 0.10` |
| `rule_of_40` | `float \| None` | Rev growth % + FCF margin %; informational |
| `earnings_quality` | `float \| None` | FCF / Net Income ratio; informational |
| `rank` | `int` | 1–20 after `rank_candidates`; 0 before |

---

## Weights Constant

```python
WEIGHTS: dict[str, float] = {
    "relative_strength":  0.30,
    "eps_revision":       0.25,
    "rating_drift":       0.15,
    "trend_quality":      0.15,
    "upside_gap":         0.10,
    "consensus_strength": 0.05,
}
```

The weights sum to exactly `1.0`. Forward-looking factors
(Relative Strength + EPS Revision + Trend Quality) total **70%**;
sell-side anchored factors total **30%**.

## Key Decisions

- **Forward weight raised to 70%** (from v2.0's 25%): Upside Gap fell
  35% → 10%, Rating Drift 25% → 15%, Consensus 15% → 5%.
- **RS window switched to 12-1**: canonical Jegadeesh-Titman; excludes
  the most recent month to sidestep short-term reversal noise.
- **Trend Quality factor added (15%)**: explicit credit for sustained
  uptrends rather than relying on the gate as a binary signal.
- **Upside Gap cap tightened to 30%** (from 50%): a single sell-side
  input cannot dominate the ranking.
- **Stress-test penalty applied directly to the score**: previously
  this was an advisory note; now over-extended names actually rank
  lower than equivalent non-extended peers.
- **Top N = 20**: matches the Leadership Board's weekly granularity.
- **Deterministic**: same inputs always produce the same output.
