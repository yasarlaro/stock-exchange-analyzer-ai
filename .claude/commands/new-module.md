---
description: Scaffold a new Python module with tests, types, docs, changelog
allowed-tools: Read, Write, Bash, Grep, Glob
---

# New Module: $ARGUMENTS

Scaffold a complete Python module named $ARGUMENTS following all AlphaVision
standards from CLAUDE.md. All commands run in WSL.

## Generate

1. **src/alphavision/$ARGUMENTS.py** — module with:
   - Module docstring + `from __future__ import annotations`
   - `logging` setup
   - Pydantic model if handling external data
   - At least one public class/function with full type hints and docstring
   - "Alternatives considered" comment block

2. **tests/test_$ARGUMENTS.py** — tests with:
   - Happy path, edge cases, exception cases
   - All yfinance/Azure Blob calls mocked
   - Coverage target >= 90%

3. **docs/$ARGUMENTS.md** — short module doc with purpose and public API

4. **CHANGELOG.md** — add entry under [Unreleased] > ### Added

## Verify Before Done
```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run pytest -W error --cov=alphavision --cov-fail-under=90
uv run python -c "import alphavision; print('OK')"
```
