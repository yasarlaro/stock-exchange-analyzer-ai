# Changelog

All notable changes to AlphaVision Equity Terminal will be documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- `pyproject.toml`: project bootstrap with hatchling, ruff, mypy, pytest config
- `src/alphavision/__init__.py`: package entry point
- `src/alphavision/universe.py`: S&P 500 + Nasdaq-100 universe builder via Wikipedia Action API
- `app.py`: Streamlit MVP UI displaying the ~520-ticker equity universe
- `docs/universe.md`: API reference for the universe module
- `README.md`: project quick-start, structure, and learning resources

### Changed
- `src/alphavision/universe.py`: switched from `pd.read_html(url)` to Wikipedia Action API to avoid 403 rate-limit; added `_fetch_wikipedia_html`, column dedup guard for NDX100 `ICB Subsector` column
- `CLAUDE.md`: added Gate 6 (Streamlit smoke test), English-only rule, docs-in-`docs/` rule, virtual environment clarification, README mandatory update rule
- `docs/CUSTOMIZATIONS.md`: updated goal coverage matrix with new rules
- `README.md`: updated project structure to reflect `docs/` reorganization

### Moved to `docs/`
- `CUSTOMIZATIONS.md` → `docs/CUSTOMIZATIONS.md`
- `SAD.md` → `docs/SAD.md`
- `METADOLOGY.md` → `docs/METADOLOGY.md`
- `ROADMAP.md` → `docs/ROADMAP.md`
