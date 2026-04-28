# AlphaVision — Implementation Roadmap

**Source of truth**: [SAD.md](SAD.md) (architecture) · [METADOLOGY.md](METADOLOGY.md) (scoring logic)

Each phase produces working, tested, committed software. No phase ends without
all five verification gates passing. Every command runs in WSL.

---

## Architecture Pipeline (from SAD.md)

```
Universe Builder → Filtering Engine → Scoring Engine → SQLite Persistence → Streamlit UI
                                                                         ↕
                                                               Azure Blob Storage
```

---

## Phase 0 — Project Bootstrap

**Goal**: Runnable Python project with correct tooling; nothing breaks.

### Deliverables

| File | Purpose |
|---|---|
| `pyproject.toml` | Project metadata, dependencies, ruff/mypy/pytest config |
| `.python-version` | Pinned Python version (latest stable) |
| `src/alphavision/__init__.py` | Package root |
| `app.py` | Streamlit entry point (empty shell) |
| `tests/__init__.py` | Test package root |
| `.gitignore` | Excludes `.venv/`, `.env`, `*.db`, `__pycache__/` |
| `CHANGELOG.md` | Empty template with `[Unreleased]` section |
| `docs/` | Empty directory for module docs |

### Commands (in WSL)

```bash
uv python pin 3.13
uv venv .venv
uv add streamlit yfinance pandas pydantic python-dotenv azure-storage-blob
uv add --dev pytest pytest-cov pytest-asyncio mypy ruff
```

### pyproject.toml required sections

```toml
[tool.ruff]
line-length = 79
select = ["E", "F", "I", "N", "W", "UP", "ANN"]

[tool.mypy]
strict = true
python_version = "3.13"

[tool.pytest.ini_options]
addopts = "-W error --cov=alphavision"
asyncio_mode = "auto"
```

### Acceptance Criteria

- [ ] `uv run streamlit run app.py` starts without error
- [ ] `uv run pytest` runs (0 tests, no failures)
- [ ] `uv run ruff check .` → clean
- [ ] `uv run mypy src/` → clean

---

## Phase 1 — MVP: Universe Builder UI ★

**Goal**: Streamlit UI that fetches all S&P 500 and Nasdaq-100 tickers from
public sources and displays them in a searchable table.

**SAD.md reference**: "Universe Builder — S&P 500 ve Nasdaq-100 birleşiminden
~520 benzersiz ticker oluşturulur."

### Deliverables

| File | Purpose |
|---|---|
| `src/alphavision/universe.py` | Fetches S&P 500 (Wikipedia) + Nasdaq-100 (Wikipedia), deduplicates, returns unified list |
| `tests/test_universe.py` | Unit tests — mock HTTP, verify dedup logic |
| `app.py` | Streamlit UI: title, loading spinner, searchable dataframe |
| `docs/universe.md` | Public API documentation |
| `CHANGELOG.md` | Entry under `[Unreleased] > ### Added` |

### `alphavision/universe.py` — Public API

```python
def get_sp500() -> pd.DataFrame:
    """Fetch S&P 500 constituents from Wikipedia.
    Returns DataFrame with columns: ticker, company, sector, sub_industry.
    """

def get_nasdaq100() -> pd.DataFrame:
    """Fetch Nasdaq-100 constituents from Wikipedia.
    Returns DataFrame with columns: ticker, company, sector.
    """

def build_universe() -> pd.DataFrame:
    """Merge S&P 500 and Nasdaq-100, deduplicate by ticker.
    Returns DataFrame with columns: ticker, company, sector, source.
    source values: 'SP500', 'NDX100', 'BOTH'
    """
```

### Streamlit UI (app.py) — Phase 1 Layout

```
AlphaVision Equity Terminal
━━━━━━━━━━━━━━━━━━━━━━━━━━
Universe: 521 unique tickers  (S&P 500: 503 | Nasdaq-100: 101 | Both: 83)

[ Search: ________________ ]

Ticker │ Company                  │ Sector           │ Source
───────┼──────────────────────────┼──────────────────┼────────
AAPL   │ Apple Inc.               │ Information Tech │ BOTH
MSFT   │ Microsoft Corp.          │ Information Tech │ BOTH
...
```

### Data Source

- S&P 500: `https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`
  Table `#0`, column `Symbol`
- Nasdaq-100: `https://en.wikipedia.org/wiki/Nasdaq-100`
  Table with `Ticker` column
- Library: `pd.read_html()` — no API key required

### Test Requirements

```python
# tests/test_universe.py
# 1. test_get_sp500_returns_dataframe_with_required_columns
# 2. test_get_nasdaq100_returns_dataframe_with_required_columns
# 3. test_build_universe_deduplicates_tickers
# 4. test_build_universe_source_column_values
# 5. test_build_universe_min_500_tickers
# 6. test_get_sp500_raises_on_network_error  (mock requests to fail)
# All HTTP calls mocked with patch("pandas.read_html")
```

### Acceptance Criteria

- [ ] `uv run streamlit run app.py` → table loads with 500+ rows
- [ ] Search box filters by ticker or company name
- [ ] Duplicate tickers appear once (source = 'BOTH')
- [ ] `uv run pytest -W error --cov=alphavision --cov-fail-under=90` passes

---

## Phase 2 — Data Fetcher

**Goal**: For each ticker in the universe, fetch the price data needed by the
filtering and scoring engines.

**METADOLOGY.md reference**: "Fiyat > 200 Günlük Hareketli Ortalama (SMA200)",
"Son 6 aylık getiri", "Analist Ortalama Hedef Fiyat / Mevcut Fiyat"

### Deliverables

| File | Purpose |
|---|---|
| `src/alphavision/data_fetcher.py` | yfinance wrapper; fetches price history and analyst data |
| `src/alphavision/models.py` | Pydantic models: `TickerData`, `AnalystData` |
| `tests/test_data_fetcher.py` | Unit tests — all yfinance calls mocked |
| `docs/data_fetcher.md` | Public API documentation |

### `alphavision/data_fetcher.py` — Public API

```python
class TickerData(BaseModel):
    ticker: str
    current_price: float
    price_6m_high: float          # 6-month peak price
    drawdown_pct: float           # (current - peak) / peak
    sma_200: float                # 200-day simple moving average
    return_6m: float              # 6-month price return
    target_mean_price: float | None
    analyst_count: int
    strong_buy_count: int
    buy_count: int
    eps_revision_direction: float # positive = upward revisions

def fetch_ticker(ticker: str) -> TickerData:
    """Fetch all required data for one ticker via yfinance."""

def fetch_universe(tickers: list[str]) -> list[TickerData]:
    """Fetch data for all tickers. Skips on error, logs warning."""
```

### Mock Pattern for Tests

```python
@pytest.fixture
def mock_yfinance():
    with patch("alphavision.data_fetcher.yf.Ticker") as mock_cls:
        t = MagicMock()
        t.info = {
            "currentPrice": 150.0,
            "targetMeanPrice": 210.0,
            "numberOfAnalystOpinions": 30,
        }
        t.history.return_value = pd.DataFrame(...)
        t.recommendations_summary = MagicMock()
        mock_cls.return_value = t
        yield mock_cls
```

### Acceptance Criteria

- [ ] `fetch_ticker("AAPL")` returns valid `TickerData`
- [ ] Network failure on one ticker does not crash `fetch_universe()`
- [ ] All yfinance calls mocked in tests — no real HTTP in test suite
- [ ] 90%+ coverage

---

## Phase 3 — Dual-Track Filtering Engine

**Goal**: Apply the two-channel entry gate from METADOLOGY.md; produce the
candidate pool that enters the scoring stage.

**METADOLOGY.md reference**:
- "Kanal A — Turnaround: Son 6 ayda zirveden en az %25 düşüş"
- "Kanal B — Momentum: Fiyat > SMA200 VE Son 6 aylık getiri > %0"

### Deliverables

| File | Purpose |
|---|---|
| `src/alphavision/filters.py` | Dual-Track filter functions |
| `tests/test_filters.py` | Unit tests with synthetic TickerData fixtures |
| `docs/filters.md` | Public API documentation |
| `app.py` update | Add "Filtered Candidates" section below Universe table |

### `alphavision/filters.py` — Public API

```python
TURNAROUND_DRAWDOWN_THRESHOLD = -0.25   # -25% from 6-month peak
MOMENTUM_SMA_MULTIPLIER = 1.0           # price > SMA200

def passes_turnaround(data: TickerData) -> bool:
    """Channel A: drawdown from 6-month peak >= 25%."""

def passes_momentum(data: TickerData) -> bool:
    """Channel B: price > SMA200 AND 6-month return > 0%."""

def apply_dual_track(universe: list[TickerData]) -> list[TickerData]:
    """Return tickers that pass Channel A OR Channel B."""
```

### Streamlit UI — Phase 3 Addition

```
Filtered Candidates  (passed Dual-Track gate)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Channel A (Turnaround): 87 stocks
Channel B (Momentum):  134 stocks
Total candidates:      198 stocks  (23 overlap)

[ table with channel column ]
```

### Acceptance Criteria

- [ ] A ticker with -30% drawdown passes Channel A
- [ ] A ticker above SMA200 with positive 6m return passes Channel B
- [ ] A ticker qualifying for both appears once in output
- [ ] A ticker below SMA200 with negative 6m return and <25% drawdown is excluded

---

## Phase 4 — Conviction Score Engine

**Goal**: Rank all candidates by the four-factor Conviction Score (0–100).
Output: ordered Top 20 list.

**METADOLOGY.md reference (v2.0)**:
1. Upside Gap (35%) = (target / current) − 1
2. Rating Drift (25%) = Strong Buy fraction as institutional conviction proxy
3. Relative Strength (15%) = 6-month return vs. SPY benchmark
4. Consensus Strength (15%) = % of Strong Buy + Buy ratings
5. EPS Momentum (10%) = direction of 12–24 month earnings revisions

### Deliverables

| File | Purpose |
|---|---|
| `src/alphavision/scoring.py` | Conviction Score calculation and Top 20 ranking |
| `src/alphavision/models.py` update | Add `ScoredTicker` Pydantic model |
| `tests/test_scoring.py` | Unit tests with synthetic data |
| `docs/scoring.md` | Public API documentation |
| `app.py` update | Replace candidate table with scored Top 20 |

### `alphavision/scoring.py` — Public API

```python
WEIGHTS = {
    "upside_gap":         0.40,
    "rating_drift":       0.30,
    "consensus_strength": 0.20,
    "eps_momentum":       0.10,
}

class ScoredTicker(BaseModel):
    ticker: str
    company: str
    conviction_score: float          # 0.0 – 100.0
    upside_gap_score: float
    rating_drift_score: float
    consensus_strength_score: float
    eps_momentum_score: float
    rank: int
    channel: str                     # 'A', 'B', or 'BOTH'

def compute_conviction_score(data: TickerData) -> ScoredTicker:
    """Compute all four sub-scores and weighted total."""

def rank_candidates(candidates: list[TickerData]) -> list[ScoredTicker]:
    """Score all candidates, rank descending, return Top 20."""
```

### Streamlit UI — Phase 4 (Main View)

```
Weekly Top 20  (run date: 2026-04-24)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Rank │ Ticker │ Company        │ Score │ Upside │ Channel │ Target Price
─────┼────────┼────────────────┼───────┼────────┼─────────┼─────────────
  1  │ NVDA   │ NVIDIA Corp.   │ 87.4  │ +42%   │ BOTH    │ $285.00
  2  │ PANW   │ Palo Alto Net. │ 82.1  │ +38%   │ B       │ $420.00
...
```

### Acceptance Criteria

- [ ] Scores are deterministic: same input → same output
- [ ] Weights sum to 1.0 (enforced via Pydantic validator)
- [ ] Ticker with no analyst data gets score = 0 without crashing
- [ ] Top 20 list is sorted by `conviction_score` descending

---

## Phase 5 — SQLite Persistence & Leadership Board

**Goal**: Persist weekly Top 20 to SQLite; compute cumulative Leadership Score
for the Leadership Board.

**SAD.md reference**: Tables `Weekly_Reports`, `Leadership_Board`.
**METADOLOGY.md reference**: "Points = (21 − Rank); Leadership Score =
Total Weekly Points × Total Weeks on List"

### Deliverables

| File | Purpose |
|---|---|
| `src/alphavision/database.py` | SQLite schema creation, read/write operations |
| `tests/test_database.py` | Unit tests — use `tmp_path` fixture, no real DB on disk |
| `docs/database.md` | Public API documentation |
| `app.py` update | Add "Leadership Board" tab |

### Database Schema (from SAD.md)

```sql
CREATE TABLE stocks (
    ticker TEXT PRIMARY KEY,
    company TEXT,
    sector TEXT
);

CREATE TABLE weekly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT,        -- ISO 8601: '2026-04-24'
    ticker TEXT,
    conviction_score REAL,
    rank INTEGER,
    upside_pct REAL,
    channel TEXT,
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);

CREATE TABLE leadership_board (
    ticker TEXT PRIMARY KEY,
    streak INTEGER,          -- current consecutive weeks in Top 20
    total_weeks INTEGER,
    total_points INTEGER,    -- sum of (21 - rank) per week
    leadership_score REAL,   -- total_points × total_weeks
    last_rank INTEGER,
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);
```

### `alphavision/database.py` — Public API

```python
def init_db(db_path: Path) -> None:
    """Create all tables if they do not exist."""

def save_weekly_report(
    db_path: Path,
    report_date: str,
    top20: list[ScoredTicker],
) -> None:
    """Persist Top 20 results and update Leadership Board."""

def get_leadership_board(db_path: Path) -> pd.DataFrame:
    """Return Leadership Board sorted by leadership_score descending."""

def get_weekly_history(db_path: Path, ticker: str) -> pd.DataFrame:
    """Return full weekly history for a single ticker."""
```

### Streamlit UI — Phase 5 (Tabs)

```
[ Universe ] [ Top 20 ] [ Leadership Board ]

Leadership Board
━━━━━━━━━━━━━━━

Rank │ Ticker │ Company      │ Streak │ Weeks │ Leadership Score
─────┼────────┼──────────────┼────────┼───────┼─────────────────
  1  │ NVDA   │ NVIDIA Corp. │  12 wk │  15   │ 2,400
  2  │ AAPL   │ Apple Inc.   │   8 wk │  22   │ 2,288
...
```

### Acceptance Criteria

- [ ] `save_weekly_report()` is idempotent for the same date
- [ ] Leadership Score = Total Points × Total Weeks (verified in tests)
- [ ] `tmp_path` used in all DB tests — no `.db` files committed
- [ ] UI switches between tabs without re-fetching data

---

## Phase 6 — Azure Blob Storage Backup

**Goal**: Weekly backup of the SQLite `.db` file to Azure Blob Storage.
Restore is possible from the latest backup.

**SAD.md reference**: "backup_to_azure() fonksiyonu her hafta SQLite .db
dosyasını Azure Blob Storage'a sürümleyerek yükler."

### Deliverables

| File | Purpose |
|---|---|
| `src/alphavision/backup.py` | Upload and restore functions |
| `tests/test_backup.py` | Unit tests — mock `BlobServiceClient` |
| `.env.example` | Template showing required env vars (no real values) |
| `docs/backup.md` | Public API documentation |

### Required `.env` Variables

```
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
AZURE_STORAGE_CONTAINER_NAME=alphavision-backups
```

### `alphavision/backup.py` — Public API

```python
def backup_to_azure(db_path: Path) -> str:
    """Upload db_path to Azure Blob Storage with timestamp versioning.

    Blob name format: alphavision_YYYYMMDD_HHMMSS.db
    Returns the blob name of the uploaded file.
    Raises EnvironmentError if AZURE_STORAGE_CONNECTION_STRING is not set.
    """

def restore_from_azure(target_path: Path) -> None:
    """Download the most recent backup blob to target_path."""
```

### Mock Pattern for Tests

```python
@pytest.fixture
def mock_blob_client():
    with patch("alphavision.backup.BlobServiceClient") as mock_cls:
        mock_container = MagicMock()
        mock_cls.from_connection_string.return_value \
            .get_container_client.return_value = mock_container
        yield mock_container
```

### Acceptance Criteria

- [ ] `backup_to_azure()` uploads a blob with timestamp in name
- [ ] Missing env var raises `EnvironmentError` with clear message
- [ ] `restore_from_azure()` downloads the most recent blob
- [ ] No real Azure calls in test suite — all mocked

---

## Summary Table

| Phase | Milestone | Key Module | UI Change |
|---|---|---|---|
| **0** | Project bootstrapped | — | `app.py` shell runs |
| **1 ★ MVP** | Universe displayed in UI | `universe.py` | Searchable ticker table |
| **2** | Price data available | `data_fetcher.py` | — (internal) |
| **3** | Candidates filtered | `filters.py` | Candidate count + channel |
| **4** | Top 20 scored & ranked | `scoring.py` | Top 20 table with scores |
| **5** | Historical data persisted | `database.py` | Leadership Board tab |
| **6** | Weekly backup live | `backup.py` | — (background) |

---

## Verification Gates (every phase)

Run in WSL before marking any phase done:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run pytest -W error --cov=alphavision --cov-fail-under=90
uv run python -c "import alphavision; print('OK')"
```

---

## Project File Structure (end state)

```
stock-exchange-analyzer-ai/
├── src/
│   └── alphavision/
│       ├── __init__.py
│       ├── __main__.py        # entry point if CLI needed
│       ├── models.py          # Pydantic: TickerData, ScoredTicker
│       ├── universe.py        # Phase 1 — S&P 500 + Nasdaq-100 builder
│       ├── data_fetcher.py    # Phase 2 — yfinance wrapper
│       ├── filters.py         # Phase 3 — Dual-Track filter
│       ├── scoring.py         # Phase 4 — Conviction Score engine
│       ├── database.py        # Phase 5 — SQLite persistence
│       └── backup.py          # Phase 6 — Azure Blob Storage
├── tests/
│   ├── __init__.py
│   ├── test_universe.py
│   ├── test_data_fetcher.py
│   ├── test_filters.py
│   ├── test_scoring.py
│   ├── test_database.py
│   └── test_backup.py
├── docs/
│   ├── universe.md
│   ├── data_fetcher.md
│   ├── filters.md
│   ├── scoring.md
│   ├── database.md
│   └── backup.md
├── app.py                     # Streamlit entry point (NOT in src/)
├── .env.example               # Required env var template
├── pyproject.toml
├── uv.lock
├── .python-version
├── CHANGELOG.md
├── CLAUDE.md
├── CUSTOMIZATIONS.md
├── ROADMAP.md
├── SAD.md
└── METADOLOGY.md
```
