# AlphaVision Investment Methodology v2.0: Multi-Factor Quality & Momentum

This document describes the mathematical filters and hybrid scoring logic used
by AlphaVision to select the highest-potential leaders from the S&P 500 and
Nasdaq-100 universe.

> **Previous version**: archived at [docs/archive/METADOLOGY_v1.md](archive/METADOLOGY_v1.md).

---

## 1. Dual-Track Filtering (Entry Gate)

Stocks must pass **at least one** of the two channels below to enter the
candidate pool:

### Channel A: Turnaround
- **Condition:** Drawdown ≥ 25% from 6-month peak.
- **Objective:** Capture "Deep Value" opportunities where analyst confidence
  remains intact but the market has oversold.

### Channel B: Momentum
- **Condition:** Price > 200-Day SMA AND 6-month return > 0%.
- **Objective:** Retain leading companies in confirmed uptrends.

---

## 2. Rule of 40 (Quality Signal)

The Rule of 40 is surfaced as a quality metric for each candidate stock. It is
**not a hard exclusion filter** — data availability varies across the universe
and applying it as a gate would systematically disadvantage capital-intensive
and commodity businesses where FCF margin data is unreliable.

**Formula:** Rule of 40 Score = Revenue Growth % + FCF Margin %

**Interpretation:**

| Score | Quality Signal |
|---|---|
| ≥ 35% | Strong — growth and cash generation are both healthy |
| 20–35% | Moderate — adequate but not exceptional |
| < 20% | Caution — growth may be consuming cash faster than warranted |

> **Note on threshold**: The 20% threshold used in some frameworks is too
> lenient for high-conviction stock selection. A ≥ 35% threshold reliably
> separates true quality compounders from marginal operators.

---

## 3. Conviction Score Algorithm (out of 100)

All candidates in the pool are scored with the following five-factor weighted
model:

1. **Upside Gap (35%):** (Analyst Mean Target Price / Current Price) - 1.
   - *Measures profit potential.*
2. **Rating Drift (25%):** Fraction of analysts with Strong Buy rating
   (institutional conviction proxy, 30-day snapshot).
   - *Measures strength of institutional conviction.*
3. **Relative Strength (15%):** Stock's 6-month return minus SPY (S&P 500
   ETF) 6-month return, normalized to [0, 100].
   - *Rewards leaders that outperform the broad market.*
4. **Consensus Strength (15%):** Percentage of Strong Buy + Buy analysts.
   - *Measures breadth of institutional consensus.*
5. **EPS Momentum (10%):** Upward revisions in future earnings estimates
   (current vs. 30-days-ago comparison).
   - *Confirms fundamental profitability improvement.*

### Weight Rationale

- **Upside Gap reduced from 40% → 35%**: Sell-side price targets carry
  inherent optimism bias. Reducing the weight prevents over-reliance on a
  single sell-side input.
- **Rating Drift reduced from 30% → 25%**: Rating Drift shares the same
  source (sell-side analysts) as Upside Gap. Reducing the combined
  sell-side weight from 70% to 60% improves signal diversity.
- **Relative Strength added at 15%**: Academic research (Jegadeesh & Titman
  1993; Fama & French 1996) consistently identifies momentum as an
  independent, statistically significant return predictor. Its absence was
  the primary methodological weakness of v1.
- **Consensus Strength reduced from 20% → 15%**: Rebalanced to accommodate
  the new Relative Strength factor without inflating sell-side representation.

### Channel A Relative Strength Neutralization

Channel A (Turnaround-only) stocks are in a drawdown by definition. Penalizing
them for negative relative performance would double-count the same price
weakness already captured by Upside Gap. Therefore:

- **Channel A only**: Relative Strength sub-score is fixed at **50 (neutral)**.
- **Channel B or BOTH**: Relative Strength sub-score uses actual outperformance
  vs. SPY benchmark.

---

## 4. Normalization Constants

| Factor | Formula | Cap / Scale |
|---|---|---|
| Upside Gap | `clamp(upside / 0.50 × 100)` | 50% upside → 100 |
| Rating Drift | `clamp(strong_buy / analyst_count × 100)` | 100% strong buy → 100 |
| Relative Strength | `clamp(50 + outperformance × 250)` | ±20% → ±50 pts from 50 |
| Consensus Strength | `clamp((sb + buy) / analyst_count × 100)` | 100% positive → 100 |
| EPS Momentum | `clamp(50 + revision × 500)` | ±10% revision → ±50 pts |

---

## 5. Leadership Rank (Stability Factor)

Stocks that remain **persistent** on the weekly list are the most reliable.

- **Scoring:** `Points = (21 - Rank)` per weekly position.
- **Leadership Score:** `Total Weekly Points × Total Weeks on List`.
- **Output:** Lists "champions" that analysts and the market have consistently
  supported for multiple weeks.

---

## 6. Eliminated Approaches and Rationale

- **RSI/MACD:** Generates excessive signal noise; does not align with the
  strategic (weekly) time horizon.
- **Social Media Sentiment:** Vulnerable to manipulation; excluded in favor of
  institutional (smart money) data.
- **P/E Ratio:** Unfairly penalizes technology and growth companies (ADBE, NOW,
  etc.); replaced by Upside Gap and Rule of 40.
- **Hard Rule of 40 Gate:** FCF data is unavailable for a significant fraction
  of universe tickers in yfinance; hard-gating would introduce survivorship
  bias. Surfaced as an informational quality signal instead.
