---
name: test
description: Write, run, and verify tests for AlphaVision modules. Zero-trust policy: every warning is a defect, every external call is mocked, 90% coverage floor.
---

# Test

## What to test
$ARGUMENTS

If $ARGUMENTS is empty, test the most recently modified module or ask
the user to specify which module or feature to test.

---

## Step 1 — Discover What Needs Testing

1. Read `CLAUDE.md` — the zero-trust testing rules apply in full.
2. Identify the target module(s) from $ARGUMENTS or recent changes:
   - Read the source file completely
   - List every public function, method, and class
   - Check `tests/` for any existing test file
   - Note which external dependencies need mocking (Azure, HTTP, DB)
3. List the test plan before writing:
   - What happy path scenarios exist
   - What edge cases and None/empty inputs are possible
   - What exceptions should be raised and when
   - Which async paths exist

---

## Step 2 — Write Tests

### File location and naming
```
src/alphavision/<module>.py  →  tests/test_<module>.py
src/alphavision/<subpkg>/<module>.py  →  tests/<subpkg>/test_<module>.py
```

### Complete test file template
```python
"""Tests for alphavision.<module_name>."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from alphavision.<module_name> import <TargetClass>, <target_function>


# ── Shared fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Minimal valid PDF for ingestion tests."""
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj")
    return pdf


@pytest.fixture
def mock_yfinance():
    """Mocked yf.Ticker that returns predictable financial data."""
    with patch("alphavision.<module_name>.yf.Ticker") as mock_cls:
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "currentPrice": 150.0,
            "targetMeanPrice": 200.0,
            "numberOfAnalystOpinions": 25,
        }
        mock_ticker.recommendations_summary = MagicMock()
        mock_cls.return_value = mock_ticker
        yield mock_cls


# ── Happy path ─────────────────────────────────────────────────────────────

class Test<ClassName>HappyPath:
    """Tests for expected-input / expected-output scenarios."""

    @pytest.fixture
    def subject(self) -> <ClassName>:
        return <ClassName>(config=MagicMock())

    def test_valid_input_returns_expected_type(self, subject) -> None:
        result = subject.method("valid_input")
        assert isinstance(result, ExpectedType)

    def test_valid_input_populates_all_fields(self, subject) -> None:
        result = subject.method("valid_input")
        assert result.field_name == expected_value
        assert result.other_field is not None


# ── Edge cases ─────────────────────────────────────────────────────────────

class Test<ClassName>EdgeCases:
    """Tests for boundary and unusual-but-valid inputs."""

    @pytest.fixture
    def subject(self) -> <ClassName>:
        return <ClassName>(config=MagicMock())

    def test_empty_string_raises_value_error(self, subject) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            subject.method("")

    def test_none_input_raises_type_error(self, subject) -> None:
        with pytest.raises(TypeError):
            subject.method(None)  # type: ignore[arg-type]

    def test_minimum_valid_length_accepted(self, subject) -> None:
        result = subject.method("A")  # single char — minimum valid
        assert result is not None


# ── Error cases ────────────────────────────────────────────────────────────

class Test<ClassName>Errors:
    """Tests for invalid inputs and exception paths."""

    @pytest.fixture
    def subject(self) -> <ClassName>:
        return <ClassName>(config=MagicMock())

    def test_invalid_ticker_raises_report_parse_error(self, subject) -> None:
        with pytest.raises(ReportParseError, match="invalid ticker"):
            subject.parse("INVALID###")

    def test_azure_error_is_propagated(self, subject) -> None:
        with patch.object(subject, "_client") as mock_client:
            mock_client.get.side_effect = AzureError("connection failed")
            with pytest.raises(AzureError):
                subject.method("valid_input")


# ── Async paths ────────────────────────────────────────────────────────────

class Test<ClassName>Async:
    """Tests for async methods."""

    @pytest.fixture
    def subject(self) -> <ClassName>:
        return <ClassName>(config=MagicMock())

    @pytest.mark.asyncio
    async def test_fetch_returns_bytes(self, subject) -> None:
        with patch("alphavision.<module>.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=MagicMock(
                    content=b"%PDF data",
                    raise_for_status=MagicMock()
                )
            )
            result = await subject.fetch_report("https://example.com/r.pdf")
            assert isinstance(result, bytes)
            assert len(result) > 0

    def test_yfinance_called_with_correct_ticker(
        self, subject, mock_yfinance
    ) -> None:
        subject.fetch_data("AAPL")
        mock_yfinance.assert_called_once_with("AAPL")
        mock_yfinance.return_value.info  # verify info was accessed
```

### Test naming convention
`test_<scenario>_<expected_outcome>`

Good examples:
- `test_valid_pdf_returns_analysis_result`
- `test_empty_ticker_raises_value_error`
- `test_expired_azure_token_triggers_credential_refresh`
- `test_malformed_json_response_raises_validation_error`

Bad examples (too vague):
- `test_works`, `test_method`, `test_parse`

---

## Step 3 — Run Unit Tests

```bash
# Run tests for the specific module first
uv run pytest tests/test_<module_name>.py -W error -v

# Then run full suite with coverage
uv run pytest -W error \
  --cov=alphavision \
  --cov-report=term-missing \
  --cov-fail-under=90
```

### If tests fail
1. Read the full error message and traceback
2. Identify root cause (not just the symptom)
3. Fix the production code OR the test (whichever is wrong)
4. Re-run the failing test in isolation first
5. Then re-run the full suite
6. Do not move forward until the suite is fully green

### If coverage is below 90%
1. Check the `--cov-report=term-missing` output for uncovered lines
2. Add targeted tests for those specific lines
3. Re-run until coverage >= 90%

---

## Step 4 — Run the Full Five-Gate Checklist

```bash
# Gate 1: Lint
uv run ruff check .

# Gate 2: Format
uv run ruff format --check .

# Gate 3: Types
uv run mypy src/

# Gate 4: Full test suite (already passed above, re-confirm clean)
uv run pytest -W error --cov=alphavision --cov-fail-under=90

# Gate 5: Application smoke test
uv run streamlit run app.py --server.headless true --help
```

---

## Step 5 — Run the Application Locally (Final Test)

This step goes beyond unit tests. Run the actual application to confirm
it behaves correctly end-to-end, not just in isolation.

### Start the application
```bash
# Start the application (choose the appropriate command for the project)
uv run streamlit run app.py --server.headless true

# OR for the API server
uv run uvicorn alphavision.api.main:app --reload --port 8000

# OR for the Streamlit UI
uv run streamlit run alphavision/ui/app.py
```

### Manual verification checklist
After the application starts, verify:
- [ ] Application starts without any error or traceback
- [ ] No DeprecationWarning or ResourceWarning in startup logs
- [ ] The feature under test is reachable (endpoint responds, UI loads)
- [ ] The feature produces correct output for a real or mocked input
- [ ] Logs look clean — no unexpected warnings or errors
- [ ] Application shuts down cleanly (Ctrl+C with no errors)

### If the application fails to start
1. Read the full traceback
2. Do NOT ignore warnings that appear during startup
3. Fix the issue — even if unit tests pass, a runtime failure is a defect
4. Re-run from Gate 4 after fixing

---

## Step 6 — Update Documentation if Tests Revealed Issues

If writing tests uncovered:
- Missing or wrong documentation → update `docs/<module>.md`
- Behavior that differs from documented behavior → fix the code or the docs
- A bug → fix it, add a regression test, add CHANGELOG entry:
  ```markdown
  ### Fixed
  - `alphavision/<module>.py`: <description of bug and fix>
  ```

---

## Completion Report Format

```
## Test Run Complete

### Scope
<which module(s) and features were tested>

### Test results
- Unit tests written: <N new tests>
- Total test suite:   <N tests>, <N passed>, <N failed>
- Coverage:           <XX%> (target >= 90%)
- Warnings promoted:  <N warnings caught and fixed>

### Gate results
- Gate 1  Ruff lint:     PASS
- Gate 2  Ruff format:   PASS
- Gate 3  Mypy:          PASS
- Gate 4  Tests:         PASS (XX%)
- Gate 5  Smoke test:    PASS

### Local application run
- Application started:  YES / NO
- Feature verified:     YES / NO
- Startup warnings:     NONE / <list any found and fixed>
- End-to-end result:    <what was observed>

### Issues found and fixed
- <issue 1>: <what it was, how it was fixed>
- <issue 2>: ...

### Remaining concerns (if any)
- <anything that could not be fully tested and why>
```
