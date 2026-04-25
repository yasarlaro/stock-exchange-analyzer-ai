# AlphaVision Equity Terminal

**AI-powered equity research and screening for the S&P 500 and Nasdaq-100.**

AlphaVision identifies the top 20 equities with maximum profit potential using a Dual-Track selection architecture: capturing both "Value" opportunities (stocks that have declined significantly) and "Momentum" winners (stocks in strong uptrends).

## Features (MVP Phase 1)

- **Universe Builder**: Fetch ~520 unique tickers from S&P 500 + Nasdaq-100
- **Searchable UI**: Filter by ticker or company name via Streamlit
- **Index Tracking**: See which tickers appear in one or both indices
- **Real-time Data**: Constituents fetched from Wikipedia, no API keys required

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Interface | Streamlit | Local dashboard & visualization |
| Data Engine | yfinance + pandas | Financial data fetching and scoring |
| Database | SQLite | Weekly reports & leadership tracking (Phase 5) |
| Cloud | Azure Blob Storage | Weekly database backup (Phase 6) |
| Language | Python 3.13 | Latest stable, typed, WSL-native |
| Package Manager | uv | Reproducible Python environments |

## Quick Start

### Prerequisites

- **Python 3.13+** (auto-downloaded by uv)
- **uv** package manager ([install here](https://docs.astral.sh/uv/getting-started/installation/))
- **WSL** (Windows Subsystem for Linux) or native Linux/macOS

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd stock-exchange-analyzer-ai
   ```

2. **Install dependencies** (creates `.venv` automatically):
   ```bash
   uv sync --dev
   ```

   `uv sync` creates `.venv` and installs all packages. You never need to
   activate it manually — always use `uv run <command>`.

   This installs:
   - `streamlit`: web UI framework
   - `yfinance`: financial data source
   - `pandas`: data manipulation
   - `pytest`, `ruff`, `mypy`: testing & linting (dev only)

### Run the Streamlit App

```bash
uv run streamlit run app.py
```

The app opens at `http://localhost:8501` in your browser.

**Features**:
- 📊 Metrics: Total tickers, S&P 500 only, Nasdaq-100 only, in both
- 🔍 Search: Filter by ticker symbol or company name
- 📋 Dataframe: Full universe with ticker, company, sector, index membership

### Run Tests

```bash
# All tests (with coverage)
uv run pytest -W error --cov=alphavision --cov-report=term-missing

# Just one test file
uv run pytest tests/test_universe.py -v

# Run with verbose output
uv run pytest -v
```

**Current coverage**: 99% (135 tests)

### Code Quality Checks

```bash
# Lint (PEP 8 + naming conventions)
uv run ruff check src/

# Format (auto-fix)
uv run ruff format src/

# Type checking (strict mode)
uv run mypy src/

# All five gates (pre-commit checklist)
uv run ruff check . && \
uv run ruff format --check . && \
uv run mypy src/ && \
uv run pytest -W error --cov=alphavision --cov-fail-under=90 && \
uv run python -c "import alphavision; print('OK')"
```

## Project Structure

```
stock-exchange-analyzer-ai/
├── src/alphavision/              # Main package
│   ├── __init__.py              # Package entry point
│   ├── models.py                # Pydantic models (TickerData, ScoredTicker)
│   ├── universe.py              # S&P 500 + Nasdaq-100 universe builder
│   ├── data_fetcher.py          # yfinance wrapper (fetch_ticker, fetch_universe)
│   ├── filters.py               # Dual-Track filter (passes_turnaround, passes_momentum)
│   └── scoring.py               # Conviction Score engine (rank_candidates, Top 20)
├── tests/                        # Test suite
│   ├── __init__.py
│   ├── test_universe.py         # Universe module tests (25 tests, 100% coverage)
│   ├── test_data_fetcher.py     # Data fetcher tests (40 tests, 97% coverage)
│   ├── test_filters.py          # Filters tests (22 tests, 100% coverage)
│   └── test_scoring.py          # Scoring tests (48 tests, 100% coverage)
├── docs/                         # All project documentation
│   ├── universe.md              # Universe module API reference
│   ├── data_fetcher.md          # Data fetcher module API reference
│   ├── filters.md               # Filters module API reference
│   ├── scoring.md               # Scoring module API reference
│   ├── METADOLOGY.md            # Dual-Track filtering methodology
│   ├── ROADMAP.md               # 7-phase implementation roadmap
│   ├── SAD.md                   # System architecture document
│   └── CUSTOMIZATIONS.md       # Claude Code customizations reference
├── app.py                        # Streamlit app entry point
├── pyproject.toml               # Project config (deps, tools, build)
├── uv.lock                      # Locked dependency versions
├── .python-version              # Python 3.13 pin
├── .gitignore                   # Git ignore rules
├── CHANGELOG.md                 # Version history
├── CLAUDE.md                    # Development instructions (auto-loaded by Claude Code)
└── README.md                    # This file
```

## Development Workflow

### Adding a New Module

Use the scaffolding command:
```bash
# Create src/alphavision/my_module.py + tests/test_my_module.py + docs/my_module.md
uv run claude-code /new-module my_module
```

Or manually:
1. Create `src/alphavision/my_module.py` with docstrings, type hints, tests
2. Create `tests/test_my_module.py` (90%+ coverage target)
3. Create `docs/my_module.md` (API reference)
4. Run all five gates above
5. Update `CHANGELOG.md`

### Committing Code

Follow [Conventional Commits](https://www.conventionalcommits.org/):
```bash
git add <files>
git commit -m "feat: add user authentication"
git commit -m "fix: handle empty yfinance responses"
git commit -m "test: increase universe builder coverage to 100%"
git commit -m "docs: update universe module API"
```

## Project Phases

| Phase | Scope | Status |
|-------|-------|--------|
| **0** | Bootstrap (pyproject.toml, .gitignore, CHANGELOG.md) | ✅ Complete |
| **1** | MVP UI (Universe Builder, Streamlit dashboard) | ✅ Complete |
| **2** | Data Fetcher (fetch financial metrics for each ticker) | ✅ Complete |
| **3** | Dual-Track Filter (apply Turnaround & Momentum filters) | ✅ Complete |
| **4** | Conviction Score (compute 100-point score per ticker) | ✅ Complete |
| **5** | SQLite Persistence (store weekly reports & leadership board) | 📋 Planned |
| **6** | Azure Blob Backup (weekly encrypted backup to cloud) | 📋 Planned |

See [docs/ROADMAP.md](docs/ROADMAP.md) for detailed phase breakdown and dependencies.

## Key Concepts

### Dual-Track Filtering

Two independent entry gates:

1. **Channel A — Turnaround**: Stock has declined ≥25% from 6-month peak
2. **Channel B — Momentum**: Price > 200-day SMA AND 6-month return > 0%

### Conviction Score (0–100)

1. **Upside Gap** (40%) = (analyst target / current price) − 1
2. **Rating Drift** (30%) = analyst rating change velocity (last 30 days)
3. **Consensus Strength** (20%) = % of Strong Buy + Buy ratings
4. **EPS Momentum** (10%) = 12–24 month earnings revision direction

### Leadership Rank

- **Weekly Points**: `21 − rank` (top stock gets 20 points)
- **Leadership Score**: Total weekly points × total weeks on list
- Tracks historical performance and consistency

## Troubleshooting

### "Module not found: alphavision"

```bash
# Recreate .venv and install all packages
uv sync --dev
# Always use uv run — never activate .venv manually
uv run python -c "import alphavision; print('OK')"
```

### Streamlit app won't start

```bash
# Check dependencies
uv run pip list | grep streamlit

# Reinstall
uv remove streamlit && uv add streamlit
```

### Tests fail with "No such file or directory"

Ensure you're in the project root:
```bash
cd /path/to/stock-exchange-analyzer-ai
uv run pytest
```

### Coverage warnings

Ignore `module-not-measured` warnings — these are expected with the `src/` layout and don't affect test success.

## Configuration

### Environment Variables

Create `.env` in the project root (gitignored):

```bash
# Optional: Azure Blob Storage connection (Phase 6)
AZURE_STORAGE_CONNECTION_STRING=...

# Optional: API keys for yfinance premium features (not needed for MVP)
# YFINANCE_API_KEY=...
```

**Do NOT commit `.env` — it's in `.gitignore`.**

### Tools Configuration

All tool configs are in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 79              # Max line length

[tool.mypy]
strict = true                 # Strict type checking

[tool.pytest.ini_options]
addopts = "-W error"          # Treat warnings as errors
```

## Contributing

1. Create a feature branch: `git checkout -b feat/my-feature`
2. Make changes + add tests
3. Run all six gates (see Code Quality Checks above + Gate 6 Streamlit smoke test)
4. Update `CHANGELOG.md` and `README.md` if behavior changed
5. Open a pull request with a descriptive title
6. Ensure CI passes (GitHub Actions, once set up)

## Learning Resources

- **Methodology**: See [docs/METADOLOGY.md](docs/METADOLOGY.md)
- **Architecture**: See [docs/SAD.md](docs/SAD.md)
- **Implementation Plan**: See [docs/ROADMAP.md](docs/ROADMAP.md)
- **Module Docs**: See [docs/universe.md](docs/universe.md)
- **Claude Code Customizations**: See [docs/CUSTOMIZATIONS.md](docs/CUSTOMIZATIONS.md)
- **Development Standards**: See [CLAUDE.md](CLAUDE.md)

## License

TBD

---

**Questions?** Check [CLAUDE.md](CLAUDE.md) for development guidelines or open an issue.
