# Changelog

All notable changes to AlphaVision Equity Terminal will be documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- `pyproject.toml`: project bootstrap with hatchling, ruff, mypy, pytest config
- `src/alphavision/__init__.py`: package entry point
- `src/alphavision/universe.py`: S&P 500 + Nasdaq-100 universe builder via Wikipedia
- `app.py`: Streamlit MVP UI displaying the ~520-ticker equity universe
- `docs/universe.md`: API reference for the universe module
