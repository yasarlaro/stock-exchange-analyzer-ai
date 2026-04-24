---
name: review
description: Review AlphaVision code against all best practices and propose concrete improvements. Read-only by default; only writes fixes if the user says "fix it" or "apply".
---

# Review

## What to review
$ARGUMENTS

If $ARGUMENTS is empty, review the entire project starting from the most
recently modified files. If a specific file or module is named, focus there
but also check its dependencies and tests.

---

## Step 1 — Map the Codebase

Before reviewing a single line:

1. Read `CLAUDE.md` — this defines what "correct" looks like.
2. Read `docs/ARCHITECTURE.md` — understand intended design.
3. Identify scope:
   - If $ARGUMENTS names a module: read that file + its test file + docs/<module>.md
   - If no scope given: list all Python files, prioritise by last-modified date
4. Read the identified files completely before writing any findings.
   Do not skim. Do not guess at content.

---

## Step 2 — Review Dimensions

Evaluate every dimension below. For each finding, always provide:
1. The specific file and line number
2. What the issue is and why it is a problem
3. A concrete better implementation (actual code, not just advice)
4. Why the better implementation is superior for this project

---

### Dimension 1: Python Standards (PEP 8 + Project Rules)

Check every Python file for:

**Formatting**
- 4-space indentation (never tabs)?
- 79-character line limit respected?
- Two blank lines between top-level definitions?
- One blank line between methods inside a class?

**Naming**
- Functions/variables: snake_case?
- Classes: PascalCase?
- Constants: UPPER_SNAKE_CASE?
- Private members: _leading_underscore?
- Any single-letter variables outside loops or math?

**Imports**
- `from __future__ import annotations` at top of every .py file?
- Import order: stdlib → third-party → local?
- Blank line between import groups?
- Any `import *`?

**Type hints**
- Every public function signature fully annotated?
- Using `str | None` not `Optional[str]`?
- Using `list[str]` not `List[str]`?
- Any implicit `Any` types?

**Docstrings**
- Every public function, method, and class has a Google-style docstring?
- Args, Returns, and Raises sections present where applicable?
- Module-level docstring present?

**Anti-patterns**
- Any `print()` in production code?
- Any `except Exception: pass`?
- Any mutable default arguments?
- Any `time.sleep()` in async code?
- Any hardcoded URLs, API keys, or thresholds?

---

### Dimension 2: Package Management

- All packages added with `uv add` (not pip)?
- `uv.lock` committed and up to date?
- `pyproject.toml` has `requires-python` set to pinned version?
- `.python-version` file present?
- Any `.venv/` files tracked by git?
- Any `requirements.txt` being used as primary source?

---

### Dimension 3: Architecture and Design

For each module, evaluate:

**Single Responsibility**
- Does each module/class do one thing clearly?
- Are there classes doing too much (God objects)?
- Are there functions longer than 30 lines that should be split?

**Dependency Direction**
- Do all external calls go through the services layer?
- Are components calling each other correctly (no circular imports)?
- Are Azure service calls properly abstracted behind interfaces?

**Error Handling**
- Are domain-specific exceptions used (not bare `Exception`)?
- Are errors logged at the right level (exception for unexpected, warning for expected)?
- Is error context preserved when re-raising?

**Configuration**
- Are all thresholds, limits, and tunable values in config/env vars?
- Is there a clear config loading pattern?

**Better implementation opportunity**
When you find an architectural issue, show the current code and the
improved version side by side:
```python
# CURRENT (problematic)
def get_score(ticker: str) -> float:
    # calls yfinance directly in business logic — untestable
    data = yf.Ticker(ticker).info
    return data["targetMeanPrice"] / data["currentPrice"]

# BETTER (dependency injection — testable)
class ScoringEngine:
    def __init__(self, fetcher: DataFetcher) -> None:
        # Alternatives considered:
        # - module-level yf calls: not testable, not mockable
        # - caching at call site: harder to control in tests
        self._fetcher = fetcher

    def compute_upside_gap(self, ticker: str) -> float:
        """Compute analyst upside gap for a ticker.
        ...
        """
```

---

### Dimension 4: Testing Quality

For each test file, evaluate:

**Coverage**
- Run: `uv run pytest --cov=alphavision --cov-report=term-missing`
- Is coverage >= 90% for each module?
- Are critical paths at 100% (Azure calls, report parsing)?

**Test quality**
- Do tests actually assert meaningful things (not just `assert True`)?
- Are all external dependencies mocked?
- Do tests cover edge cases and exception paths?
- Are test names descriptive (`test_empty_pdf_raises_parse_error`)?
- Are there any xfail or skip markers without a linked issue?

**Warnings**
- Run: `uv run pytest -W error`
- Does the suite pass with warnings promoted to errors?
- Any DeprecationWarning suggesting an API upgrade is needed?

**For every gap found, provide the missing test:**
```python
# MISSING: test for when Azure OpenAI returns malformed JSON
@pytest.mark.asyncio
async def test_malformed_json_response_raises_validation_error(
    subject, mock_azure_openai
) -> None:
    mock_azure_openai.chat.completions.create = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="not json"))]
        )
    )
    with pytest.raises(ValidationError, match="Invalid JSON"):
        await subject.analyze("report content")
```

---

### Dimension 5: Security

**Secrets and credentials**
- Any hardcoded API keys, tokens, passwords, connection strings?
  Scan: `grep -rn "api_key\|secret\|password\|Bearer " src/`
- All Azure calls using `DefaultAzureCredential`?
- Azure Connection String loaded from `.env` / environment variable (never hardcoded)?

**Input validation**
- All external inputs (report URLs, user-provided tickers) validated?
- Pydantic models enforced at all service boundaries?
- Any LLM responses used without validation?

**Prompt injection risk**
- System prompt separated from user/report content?
- `response_format={"type": "json_object"}` used for structured output?
- No raw report content interpolated into system instructions?

**Dependencies**
- Run: `uv run pip-audit`
- Any known CVEs in current dependency versions?

---

### Dimension 6: Performance and Efficiency

**Async usage**
- All I/O-bound operations (HTTP, Azure, DB) using async?
- No `asyncio.run()` called from within an async context?
- Connection pools / clients reused across calls (not recreated per request)?

**Unnecessary work**
- Any repeated expensive operations that should be cached?
- Any N+1 query patterns (fetching data in a loop that could be batched)?
- Any synchronous calls inside async functions?

**Context window efficiency (for AI calls)**
- Are prompts as concise as possible while still being precise?
- Is report content chunked before sending to Azure OpenAI?
- Is `response_format` used to avoid parsing unstructured output?

---

### Dimension 7: Documentation

**In-code documentation**
- Every public API has a complete Google-style docstring?
- "Alternatives considered" comment present on non-trivial choices?
- No stale comments describing old behavior?

**docs/ directory**
- docs/<module>.md exists for every module?
- Documented function signatures match actual signatures?
- Usage examples work (copy-paste and run)?

**CHANGELOG.md**
- [Unreleased] section kept up to date?
- Entries are specific (not "updated code" or "fixed bug")?

---

## Step 3 — Run All Automated Checks

Run these and include the full output in your findings:

```bash
# Lint
uv run ruff check .

# Format
uv run ruff format --check .

# Type checking
uv run mypy src/

# Tests with warnings promoted to errors
uv run pytest -W error \
  --cov=alphavision \
  --cov-report=term-missing

# Security scan
uv run pip-audit

# Secrets scan (grep — no external tool needed)
grep -rn "api_key\|password\|secret\|Bearer\|sk-" src/ \
  --include="*.py" \
  --exclude-dir=__pycache__
```

---

## Step 4 — Propose Concrete Improvements

For EVERY finding, provide:

```
[BLOCKING] | [HIGH] | [MEDIUM] | [LOW] | [SUGGESTION]

File: src/alphavision/<module>.py  Line: <N>
Issue: <specific description of the problem>
Why it matters: <impact on this project — not generic advice>

Current code:
    <the actual problematic code>

Better implementation:
    <the actual improved code>

Why better:
    <specific reason relating to AlphaVision — testability, performance,
     security, maintainability — not just "it's cleaner">
```

Severity guide:
- **BLOCKING**: security risk, data loss potential, crashes at runtime
- **HIGH**: breaks zero-trust testing, circumvents type system, architectural violation
- **MEDIUM**: coverage gap, missing docstring on public API, wrong error handling
- **LOW**: naming convention, comment quality, minor style inconsistency
- **SUGGESTION**: valid alternative worth considering, not a defect

---

## Step 5 — Apply Fixes (only if user says "fix it" or "apply")

If the user explicitly asks to apply the review findings:

1. Apply BLOCKING issues first, then HIGH, MEDIUM, LOW
2. After each fix: re-run the relevant gate (ruff / mypy / pytest)
3. After all fixes: run the full five-gate checklist
4. Update docs/<module>.md and CHANGELOG.md for any API changes
5. Delete any temporary files

---

## Completion Report Format

```
## Review Complete

### Scope
<which files and modules were reviewed>

### Automated check results
- Ruff lint:     PASS / FAIL (<N issues>)
- Ruff format:   PASS / FAIL (<N files>)
- Mypy:          PASS / FAIL (<N errors>)
- Tests:         PASS / FAIL (<N%, target 90%>)
- pip-audit:     PASS / FAIL (<N CVEs>)
- Secrets scan:  CLEAN / FOUND (<N matches>)

### Findings summary
- BLOCKING:    <N>
- HIGH:        <N>
- MEDIUM:      <N>
- LOW:         <N>
- SUGGESTIONS: <N>

### Detailed findings
<full list using the format above>

### Top 3 improvements recommended
1. <most impactful change with concrete implementation>
2. <second most impactful>
3. <third most impactful>

### Overall assessment
<2–3 sentence honest assessment of the codebase health>
HEALTHY | NEEDS ATTENTION | CRITICAL ISSUES FOUND
```
