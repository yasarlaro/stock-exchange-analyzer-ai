# AlphaVision Investment Methodology v3.0: Forward-Momentum Alpha

This document describes the entry gate and scoring engine used by
AlphaVision to identify equities with the highest growth potential over
the next 6 months from the S&P 500 + Nasdaq-100 universe.

> **Previous versions** (archived):
> - [docs/archive/METADOLOGY_v1.md](archive/METADOLOGY_v1.md) — v1.0
>   single-track Conviction Score.
> - [docs/archive/METADOLOGY_v2.md](archive/METADOLOGY_v2.md) — v2.0
>   Dual-Track filter + multi-factor score. Replaced because Channel A
>   (Turnaround) and the 35% Upside Gap weight produced a structural
>   "Mean Reversion Bias" — the v2.0 Top 20 evaluated 2026-04-27 was
>   dominated 20-of-20 by Fallen Angel tickers in active drawdown.

---

## 1. Forward-Momentum Filter (Entry Gate)

A ticker must pass **all four** gates to enter the candidate pool:

| # | Gate | Condition | Purpose |
|---|---|---|---|
| 1 | Long-term trend | `current_price > sma_200` | Ensures the long-term trend is up. |
| 2 | Intermediate momentum | `return_12_1 > 0` | Positive Jegadeesh-Titman 12-1 return: total return from ~12 months ago to ~1 month ago, excluding the most recent month to sidestep short-term reversal noise. |
| 3 | Not over-extended | `current_price ≤ 1.15 × sma_20` | Excludes climactic blow-off tops where mean-reversion risk is acute. |
| 4 | Coverage floor | `analyst_count ≥ 3` | Ensures analyst-driven sub-scores have a statistically meaningful denominator. |

> **Why no Channel A (Turnaround)?** v2.0's Channel A admitted any ticker
> with a ≥25% drawdown. Combined with the v2.0 35% Upside Gap weight
> (which mechanically inflates as price falls but analyst targets lag),
> this guaranteed Fallen Angels would dominate the ranking. Turnaround
> is a 12–24 month thesis; it does not belong in a 6-month
> forward-momentum mandate.

---

## 2. Conviction Score Algorithm (out of 100)

Survivors of the entry gate are scored with a six-factor weighted
model. **Forward-looking factors total 70%; sell-side anchored
factors total 30%.**

| # | Factor | Weight | Class |
|---|---|---|---|
| 1 | Relative Strength (12-1) | **30%** | Forward |
| 2 | EPS Revision Momentum | **25%** | Forward |
| 3 | Trend Quality (price vs SMA-200) | **15%** | Forward |
| 4 | Rating Drift (Strong-Buy fraction) | **15%** | Sell-side |
| 5 | Upside Gap (analyst target) | **10%** | Sell-side |
| 6 | Consensus Strength (Buy + Strong-Buy) | **5%** | Sell-side |

### 2.1 Relative Strength (12-1) — 30%

The canonical Jegadeesh-Titman momentum factor.

```
rs_12_1 = stock.return_12_1 − SPY.return_12_1
score   = clamp(50 + rs_12_1 × 200,  0, 100)
```

±25% relative outperformance over the 12-1 window maps to a ±50-point
sub-score swing.

### 2.2 EPS Revision Momentum — 25%

Forward-EPS revision direction over the trailing 30 days, computed
from `yfinance` `get_eps_trend()`.

```
revision = (current_eps − eps_30d_ago) / |eps_30d_ago|
score    = clamp(50 + revision × 500,  0, 100)
```

±10% revision maps to a ±50-point sub-score swing.

### 2.3 Trend Quality — 15%

How decisively above the 200-day SMA the price is trading.

```
deviation = current_price / sma_200 − 1
score     = clamp(50 + deviation × 200,  0, 100)
```

A price 25% above SMA-200 yields the maximum sub-score of 100.

### 2.4 Rating Drift — 15%

Strong-Buy fraction as a proxy for institutional conviction.

```
score = clamp(strong_buy_count / analyst_count × 100,  0, 100)
```

### 2.5 Upside Gap — 10% (cap tightened from v2.0's 50% to 30%)

Analyst mean target relative to current price.

```
upside = target_mean_price / current_price − 1
score  = clamp(upside / 0.30 × 100,  0, 100)
```

The 30% cap (vs. v2.0's 50%) deliberately compresses the range so that
a single sell-side input cannot dominate the ranking. Upside drops from
v2.0's leading 35% weight to a sanity-check 10%.

### 2.6 Consensus Strength — 5%

Light breadth check on positive ratings.

```
score = clamp((strong_buy_count + buy_count) / analyst_count × 100,
              0, 100)
```

---

## 3. Stress-Test Penalty

After computing the weighted total, the score is dampened if the
ticker is stretched well above its 20-day SMA:

```
extension_pct = current_price / sma_20 − 1
if extension_pct > 0.10:
    conviction_score *= 0.90
```

The entry gate already excludes anything stretched above 1.15 × SMA-20;
the penalty band is therefore narrow (10–15%) but it discourages
chasing names that are already "extended" within the candidate pool.

The diagnostic `extension_pct` and an `over_extended` boolean are
persisted on every `ScoredTicker` so reviewers can see at a glance how
far above SMA-20 each name is trading.

---

## 4. Normalisation Constants

| Factor | Formula | Reference Point |
|---|---|---|
| Relative Strength | `clamp(50 + rs_12_1 × 200)` | ±25% RS → sub-score 100 / 0 |
| EPS Revision | `clamp(50 + revision × 500)` | ±10% revision → 100 / 0 |
| Trend Quality | `clamp(50 + (price/sma200 − 1) × 200)` | +25% above SMA → 100 |
| Rating Drift | `clamp(strong_buy / analyst_count × 100)` | 100% Strong Buy → 100 |
| Upside Gap | `clamp(upside / 0.30 × 100)` | 30% upside → 100 |
| Consensus | `clamp((sb + buy) / analyst_count × 100)` | 100% positive → 100 |

---

## 5. Leadership Rank (Stability Factor)

Stocks that remain **persistent** on the weekly list are the most
reliable.

- **Scoring:** `Points = (21 − Rank)` per weekly position.
- **Leadership Score:** `Total Weekly Points × Total Weeks on List`.
- **Output:** Lists "champions" that the algorithm has consistently
  ranked over multiple weeks.

---

## 6. Key Decisions vs. v2.0

| Change | v2.0 | v3.0 | Reason |
|---|---|---|---|
| Channel A (Turnaround) | ≥25% drawdown gate | **Removed** | Mean-reversion bias; mismatched horizon (12–24m vs. 6m mandate). |
| Channel B (Momentum) | `price > SMA200 AND return_6m > 0` | `price > SMA200 AND return_12_1 > 0` (+ extension cap, + analyst floor) | 12-1 window ex-recent reversal noise; explicit non-blow-off and coverage gates. |
| Upside Gap weight | 35% (leading) | 10% | Reduces sell-side dependence; a stale target on a depressed price is no longer the dominant signal. |
| Upside Gap cap | 50% | 30% | Compresses range; one sell-side input cannot dominate. |
| Relative Strength | 6m, 15% | **12-1, 30%** | Canonical Jegadeesh-Titman window; doubled weight. |
| EPS Momentum | 10% | 25% | Forward earnings revisions are the most reliable 6-month return predictor. |
| Trend Quality | n/a | 15% | New: surfaces strength of the long-term uptrend explicitly. |
| Channel A RS bypass | RS = 50 fixed | n/a | Removed with Channel A. |
| Stress-test penalty | n/a | ×0.90 if `price > 1.10 × SMA-20` | Discourages chasing stretched names within the candidate pool. |
| SPY benchmark fetch | `fetch_ticker(SPY)` (404s on `.info`) | `yf.Ticker(SPY).history()` | Bug fix: ETF fundamentals endpoint is unavailable; v2.0 silently fell back to a benchmark of 0. |

**Net effect**: combined sell-side weight drops from 75% → 30%; combined
forward-looking weight rises from 25% → 70%.

---

## 7. Eliminated Approaches and Rationale

- **RSI / MACD:** generates excessive signal noise; misaligned with the
  weekly-cadence horizon.
- **Social-media sentiment:** vulnerable to manipulation; institutional
  data is preferred.
- **P/E ratio:** unfairly penalises growth names; replaced by Upside
  Gap and informational Rule of 40.
- **Hard Rule of 40 gate:** FCF data is unavailable for a significant
  fraction of universe tickers; surfaced as an informational quality
  signal instead.
- **Channel A (Turnaround):** structural mean-reversion bias on a
  forward-momentum mandate (see v6 above).
- **Quantile gates / sector-relative scoring:** non-deterministic or
  high-complexity for marginal gain at the MVP phase.
