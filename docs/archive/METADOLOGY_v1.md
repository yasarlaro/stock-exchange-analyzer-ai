# AlphaVision Investment Methodology v1.0 (Archived)

> **Status**: Superseded by [docs/METADOLOGY.md](../METADOLOGY.md) (v2.0).
> Kept for historical reference only. Do not use this version.

---

## 1. Dual-Track Filtering (Entry Gate)

Stocks must pass **at least one** of the two channels to enter the candidate pool:

### Channel A: Turnaround
- **Condition:** Drawdown ≥ 25% from 6-month peak.
- **Objective:** Capture "Deep Value" opportunities where analyst confidence
  remains intact but the market has oversold.

### Channel B: Momentum
- **Condition:** Price > 200-Day SMA AND 6-month return > 0%.
- **Objective:** Retain leading technology companies in confirmed uptrends
  (NVIDIA, Apple, etc.) from being filtered out.

---

## 2. Conviction Score Algorithm (out of 100)

All candidates were scored with the following four-factor weighted model:

1. **Upside Gap (40%):** (Analyst Mean Target Price / Current Price) - 1.
   - *Directly measures maximum profit potential.*
2. **Rating Drift (30%):** Analyst rating change velocity, last 30 days.
   - *Measures whether analyst confidence in the stock is increasing.*
3. **Consensus Strength (20%):** Percentage of "Strong Buy" + "Buy" analysts.
   - *Measures institutional consensus breadth.*
4. **EPS Momentum (10%):** Upward revisions in 12–24 month earnings estimates.
   - *Confirms fundamental profitability improvement.*

---

## 3. Leadership Rank (Stability Factor)

Stocks that remain **persistent** on the weekly list are the most reliable.

- **Scoring:** `Points = (21 - Rank)` per weekly position.
- **Leadership Score:** `Total Weekly Points × Total Weeks on List`.
- **Output:** Lists "champions" that analysts have consistently supported for
  multiple weeks — lowest margin of error.

---

## 4. Eliminated Approaches and Rationale

- **Social Sentiment:** Vulnerable to manipulation; excluded in favor of
  institutional (smart money) data only.
- **Pure Technicals (RSI/MACD):** Do not answer the "why" question; removed
  from primary scoring; kept as secondary confirmation only.
- **Fixed 25% Drawdown Only:** Eliminated winning stocks; resolved by adopting
  the Dual-Track architecture.
