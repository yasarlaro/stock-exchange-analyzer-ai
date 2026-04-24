# Universe Module

**Purpose**: Fetches and merges the S&P 500 and Nasdaq-100 constituent lists
from Wikipedia into a single deduplicated equity universe.

## Public API

### `get_sp500() -> pd.DataFrame`

Fetches current S&P 500 constituents from Wikipedia.

**Returns**: DataFrame with columns `ticker`, `company`, `sector`.

**Raises**: `RuntimeError` — if the Wikipedia page cannot be parsed.

**Example**:

    df = get_sp500()
    # Returns ~503 rows

---

### `get_nasdaq100() -> pd.DataFrame`

Fetches current Nasdaq-100 constituents from Wikipedia.

**Returns**: DataFrame with columns `ticker`, `company`, `sector`.

**Raises**: `RuntimeError` — if the Wikipedia page cannot be parsed.

**Example**:

    df = get_nasdaq100()
    # Returns ~101 rows

---

### `build_universe() -> pd.DataFrame`

Combines both index lists, deduplicates, and tags each ticker with its
index membership.

**Returns**: DataFrame with columns `ticker`, `company`, `sector`, `source`
where `source` is one of `"SP500"`, `"NDX100"`, or `"BOTH"`.
Sorted alphabetically by `ticker`.

**Raises**: `RuntimeError` — if either constituent list cannot be fetched.

**Example**:

    universe = build_universe()
    # Returns ~520 rows (varies with index rebalancing)
    both = universe[universe["source"] == "BOTH"]

## Data Source

Both lists are fetched from Wikipedia using `pd.read_html()` targeting
the `#constituents` table on each page. No API key or registration required.
Suitable for weekly refresh cadence.

## Configuration

No environment variables required. All data is public.
