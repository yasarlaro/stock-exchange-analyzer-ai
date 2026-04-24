---
name: implement
description: Implement a new feature or module in AlphaVision. Follows all project rules: uv, PEP 8, type hints, Google docstrings, Alternatives Considered, zero-trust testing, and the five-gate pre-completion checklist.
---

# Implement

## What to implement
$ARGUMENTS

If $ARGUMENTS is empty or too vague to act on, ask the user ONE clarifying
question before proceeding. Do not ask multiple questions at once.

---

## Step 1 — Understand Context First

Before writing a single line of code:

1. Read `CLAUDE.md` — internalize every rule in it.
2. Read `docs/ARCHITECTURE.md` — understand the system data flow.
3. Search the codebase for related existing code:
   - Look for similar patterns to follow
   - Identify if any part of the work already exists
   - Identify which module(s) the new code belongs in
4. Identify which Azure services are required (if any).
5. State a brief plan (2–5 bullet points) before coding.
   List every file that will be created or modified.

---

## Step 2 — Implement the Code

### Environment rules (non-negotiable)
- Add packages with `uv add <pkg>` — never `pip install`
- Run scripts with `uv run <script>` — never `python <script>`
- Virtual environment is always `.venv`

### Every new Python file must start with
```python
"""<One-line module description>."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)
```

### Coding standards
- 4-space indentation, 79-character line limit
- Naming: snake_case functions/vars, PascalCase classes,
  UPPER_SNAKE_CASE constants, _leading_underscore private members
- Imports: stdlib → third-party → local, blank line between groups
- Full type annotations on every function signature:
  `str | None` not `Optional[str]`, `list[str]` not `List[str]`
- Google-style docstring on every public function, method, and class:
  Args / Returns / Raises sections required
- Never print() in production — use logger.info() / logger.exception()
- Never `except Exception: pass` — catch specific, log, re-raise
- Never mutable default arguments — use None sentinel
- Never hardcode URLs, credentials, thresholds — use env vars or config

### Pydantic for all data crossing boundaries
Use `pydantic.BaseModel` for any data that crosses module or service
boundaries. Validate at the edges; trust validated data inside.

### Azure authentication
Always `DefaultAzureCredential` — no API keys in code.
Use async Azure clients (.aio variants) for all I/O operations.

### Alternatives Considered — required for every non-trivial choice
Add immediately after the docstring:
```python
# Alternatives considered:
# - <option A>: rejected because <specific reason relating to this project>
# - <option B>: rejected because <specific reason relating to this project>
```

---

## Step 3 — Write Tests Immediately (same session)

Create `tests/test_<module_name>.py` alongside every new or changed module.
Do not defer tests to a later session.

### Required test categories per module
1. Happy path — valid inputs produce correct, fully-typed output
2. Edge cases — empty string, None, zero, boundary values
3. Error cases — invalid input raises correct exception with correct message
4. Async paths — @pytest.mark.asyncio + AsyncMock for every async method
5. Side effects — mock ALL external calls: Azure, HTTP, filesystem, DB

### yfinance mock pattern
```python
@pytest.fixture
def mock_yfinance():
    with patch("alphavision.<module>.yf.Ticker") as mock_cls:
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "currentPrice": 150.0,
            "targetMeanPrice": 200.0,
            "numberOfAnalystOpinions": 25,
        }
        mock_ticker.recommendations_summary = MagicMock()
        mock_cls.return_value = mock_ticker
        yield mock_cls
```

### Coverage target
- New modules: >= 90% line coverage
- Critical paths (AI calls, report parsing, Azure calls): 100%

---

## Step 4 — Run the Five-Gate Checklist

Run all five in order. Fix every failure before proceeding.
Do NOT report completion until all five show zero errors or failures.

```bash
# Gate 1: Lint
uv run ruff check .

# Gate 2: Format
uv run ruff format --check .

# Gate 3: Type checking
uv run mypy src/

# Gate 4: Tests with warnings-as-errors and coverage
uv run pytest -W error \
  --cov=alphavision \
  --cov-report=term-missing \
  --cov-fail-under=90

# Gate 5: Application smoke test
uv run python -c "import alphavision; print('AlphaVision import: OK')"
```

If a gate fails: fix → re-run that gate → re-run all previous gates → continue.

---

## Step 5 — Update Documentation (same session)

### Create or update docs/<module_name>.md
```markdown
# <Module Name>

**Purpose**: <one sentence>

## Public API

### `function_name(param: Type) -> ReturnType`
<one-line description>
**Raises**: `ExceptionType` — if <condition>

**Example**:
    result = function_name("input")

## Azure Dependencies
- <service name>: <purpose>

## Configuration
- `ENV_VAR_NAME`: <what it controls>
```

### Add to CHANGELOG.md under [Unreleased]
```markdown
### Added
- `src/alphavision/<module>.py`: <one-line description>

### Changed  (only if modifying existing code)
- `src/alphavision/<module>.py`: <what changed and why>
```

---

## Step 6 — Clean Up

Before marking complete:
- Delete any temporary files created during this session:
  debug_*.py  scratch_*.py  test_manual_*.py  *_temp.json  output_debug.*
- Confirm no .env, .key, .pem files were created
- Confirm .venv/ was not modified in a way that would be committed

---

## Completion Report Format

```
## Implementation Complete

### What was implemented
<one paragraph describing what now exists and what problem it solves>

### Files created
- src/alphavision/<module>.py — <purpose>
- tests/test_<module>.py — <X tests, Y% coverage>
- docs/<module>.md — API reference

### Files modified
- CHANGELOG.md — [Unreleased] entry added
- <any other modified files>

### Verification results
- Gate 1  Ruff lint:     PASS
- Gate 2  Ruff format:   PASS
- Gate 3  Mypy:          PASS
- Gate 4  Tests:         PASS (coverage: XX%)
- Gate 5  Smoke test:    PASS

### Key decisions
- <decision 1>: chose X over Y because <reason specific to AlphaVision>
- <decision 2>: chose A over B because <reason>
```
