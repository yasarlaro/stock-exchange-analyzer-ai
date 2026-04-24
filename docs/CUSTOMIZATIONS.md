# Claude Customizations Reference — AlphaVision

All implemented customizations for the AlphaVision Equity Terminal project.

---

## Project Instructions

| File | Purpose | Active Per Chat | Trigger |
|---|---|---|---|
| [CLAUDE.md](../CLAUDE.md) | Project identity, persona, tech stack, coding standards, WSL policy, venv policy, language policy, testing policy, documentation rules, temp file rules, pre-completion checklist | ✅ Always (auto-loaded) | Every conversation |

**What CLAUDE.md makes agents understand automatically:**
- Project: AlphaVision Equity Terminal (S&P 500 + Nasdaq-100, Dual-Track, Conviction Score)
- Persona: 4 hats — AI Architect, QA Tech Lead, DevOps Expert, Documentation Owner
- Tech stack: Streamlit · SQLite · yfinance/Pandas · Azure Blob Storage · uv
- WSL policy: All commands run in WSL; never Windows PowerShell or CMD
- **Virtual environment**: `.venv` managed by `uv sync`; always use `uv run` — never activate manually
- **Language**: All code, comments, docstrings, and documentation must be in English. User may write in Turkish; project artifacts must not.
- Standards: PEP 8, type hints, Google docstrings, 90%+ test coverage
- Zero-trust: warnings = defects, mock all external calls, don't exit without tests passing
- **UI testing required**: Gate 6 — start Streamlit and confirm HTTP 200 before marking any UI task done. Unit tests verify logic, not rendering.
- **Docs location**: all `.md` files except `README.md` and `CHANGELOG.md` go in `docs/`
- **Docs update**: `docs/<module>.md` + `CHANGELOG.md` + `README.md` (if user-visible change) updated in same commit as code
- Cleanup: temp files (`debug_*.py`, `scratch_*.py`, `*_temp.json`) deleted before done

---

## Runtime Configuration

| File | Purpose | Active Per Chat | What It Enforces |
|---|---|---|---|
| [.claude/settings.json](.claude/settings.json) | Model selection, permissions, security hooks | ✅ Always (harness-level) | See hook table below |

### Allowed Bash Commands
```
uv:*     git:*     ruff:*     mypy:*     pytest:*     az:*
```

### Blocked Actions
```
Bash(pip install:*)   — forces uv add
Read/Write(.env*)     — protects secrets
Write(.venv/**)       — protects virtual env
Write(*.key, *.pem)   — protects credentials
```

### Automatic Hooks

| Hook | When | Action |
|---|---|---|
| Pre-Write | Write to `.env`, `secrets/`, `.key`, `.pem` | DENY — blocks the write |
| Pre-Bash | Command contains `pip install` | DENY — outputs "Use uv add" |
| Post-Write | Any `.py` file written | Runs `ruff check` + `ruff format --check`; warns on failure |
| Stop | Session ends | Deletes `debug_*.py`, `scratch_*.py`, `test_manual_*.py`, `*_temp.json` |

---

## Editor Configuration

| File | Purpose | Active Per Chat |
|---|---|---|
| [.vscode/settings.json](.vscode/settings.json) | Python formatter (ruff), interpreter path (`.venv`), file exclusions, `chat.useClaudeMdFile: true` | ✅ Always (VSCode-level) |
| [.vscode/mcp.json](.vscode/mcp.json) | MCP servers: GitHub API, Azure resource management, Playwright browser automation | ✅ Always (VSCode-level) |

---

## Skills (`/skill-name`)

Skills are invoked by the user with `/skill-name` and run in the main conversation.

| Skill | File | Trigger | Purpose |
|---|---|---|---|
| **implement** | [.claude/skills/implement/SKILL.md](.claude/skills/implement/SKILL.md) | `/implement <description>` | Full implementation: code + tests + docs + 5-gate checklist |
| **review** | [.claude/skills/review/SKILL.md](.claude/skills/review/SKILL.md) | `/review [file]` | Structured code review with concrete fix proposals across 7 dimensions |
| **test** | [.claude/skills/test/SKILL.md](.claude/skills/test/SKILL.md) | `/test [module]` | Write tests, run suite, verify 90%+ coverage, smoke test |

---

## Commands (`/command-name`)

Commands are reusable workflow scripts invoked with `/command-name`.

| Command | File | Trigger | Purpose |
|---|---|---|---|
| **verify-all** | [.claude/commands/verify-all.md](.claude/commands/verify-all.md) | `/verify-all` | Runs 5-gate checklist: ruff lint/format, mypy, pytest 90%+, import smoke test |
| **new-module** | [.claude/commands/new-module.md](.claude/commands/new-module.md) | `/new-module <name>` | Scaffolds module + tests + docs + CHANGELOG entry |

---

## Sub-Agents (`.claude/agents/`)

Sub-agents are spawned by Claude Code for focused, isolated work on large tasks.

| Agent | File | Model | Purpose |
|---|---|---|---|
| **Implementer** | [.claude/agents/implementer.md](.claude/agents/implementer.md) | sonnet | Write code + tests + docs; runs full verification before done |
| **Planner** | [.claude/agents/planner.md](.claude/agents/planner.md) | opus | Architecture and implementation planning only — read-only, no code changes |
| **Reviewer** | [.claude/agents/reviewer.md](.claude/agents/reviewer.md) | opus | Structured code review — read-only, no code changes |

---

## Goal Coverage Matrix

| User Goal | How It Is Met | File |
|---|---|---|
| Project identity & architecture | Project Overview, pipeline, tech stack, methodology | CLAUDE.md |
| Persona auto-detection | Four Hats section | CLAUDE.md |
| Tech stack | Streamlit, SQLite, yfinance, Azure Blob, uv | CLAUDE.md |
| Coding standards | PEP 8, type hints, docstrings, import order | CLAUDE.md |
| WSL-only execution | Execution Environment — WSL Policy section | CLAUDE.md |
| Virtual environment via uv | Virtual Environment section (uv sync + uv run) | CLAUDE.md |
| English-only artifacts | Language — English Only section | CLAUDE.md |
| All docs in docs/ | Project Structure Rules section | CLAUDE.md |
| README + CHANGELOG always in sync | Documentation Maintenance section | CLAUDE.md |
| Zero-trust / validation loop | QA Tech Lead persona + Testing section + 6-gate checklist | CLAUDE.md |
| UI smoke test before done | Gate 6 in Mandatory Pre-Completion Checklist | CLAUDE.md |
| Documentation requirements | Documentation Maintenance section | CLAUDE.md |
| Temp file cleanup | Temporary Files section + Stop hook | CLAUDE.md + settings.json |
| Implement workflow | `/implement` skill (6-step protocol, code+tests+docs) | skills/implement/ |
| Review workflow | `/review` skill (7 dimensions, automated checks, fix proposals) | skills/review/ |
| Test workflow | `/test` skill (write+run+verify+smoke test) | skills/test/ |

---

## Deleted Files (with rationale)

| File | Reason Deleted |
|---|---|
| `.claude/settings.local.json` | Hardcoded Windows PowerShell paths — contradicted WSL policy |
| `.claude/skills/python-standards/` | Fully covered by CLAUDE.md Coding Standards section |
| `.claude/skills/report-analysis/` | FinAnalyst-specific (PDF parsing + Azure Document Intelligence + Azure OpenAI) — not applicable to AlphaVision |
| `.claude/skills/test-writer/` | Strict subset of the `test` skill; `test` writes AND runs AND verifies |
| `.claude/skills/azure-integration/` | FinAnalyst Azure stack (OpenAI, Document Intelligence, Key Vault, Bicep) — AlphaVision only uses Azure Blob Storage via `.env` |
| `.claude/skills/security-audit/` | FinAnalyst-specific checks; overlap with reviewer agent's security dimension |
| `.claude/commands/security-review.md` | Duplicate of security dimension in `review` skill; referenced `DefaultAzureCredential` (not used in AlphaVision) |
