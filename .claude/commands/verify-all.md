---
description: Run the full AlphaVision verification checklist
allowed-tools: Bash
---

# Full Verification Checklist

Run all five gates in WSL and report results:

```bash
echo "=== 1. Ruff Lint ==="
uv run ruff check .

echo "=== 2. Ruff Format ==="
uv run ruff format --check .

echo "=== 3. Mypy ==="
uv run mypy src/

echo "=== 4. Tests + Coverage ==="
uv run pytest -W error --cov=alphavision --cov-fail-under=90 --cov-report=term-missing

echo "=== 5. Application Smoke Test ==="
uv run python -c "import alphavision; print('AlphaVision import: OK')"
```

Report:
- PASS or FAIL for each gate
- For failures: file name, line number, error message
- Overall: ALL PASS (safe to commit) or FAILURES FOUND (do not commit)
