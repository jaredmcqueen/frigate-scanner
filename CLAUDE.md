# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->


## Build & Test

```bash
# Install dependencies (uses uv lockfile)
uv sync

# Run full test suite
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing

# Lint / format
uv run ruff check src tests
uv run ruff format src tests
```

## Single Daily Command

```bash
# Scan Shodan, probe open instances, persist to SQLite, print summary
uv run src/backend/run.py run

# View results in the web dashboard
uv run src/backend/run.py serve
```

Requires `SHODAN_API_KEY` in `.env` (copy `.env.example`).

## Architecture Overview

```
src/backend/
  run.py                        # CLI entrypoint — two subcommands: run, serve
  frigate_scanner/
    search.py                   # Shodan queries → list of host dicts
    probe.py                    # Async /api/stats probing → open instances
    store.py                    # SQLite persistence + diff vs. previous scan
    report.py                   # HTML renderer + JSONL/HTML writers (utilities)
    dashboard.py                # FastAPI app serving live card view from DB
```

**Data flow:** `search` → `probe` → `store` (SQLite `frigate.db`) → terminal summary.
The `serve` command reads from `frigate.db` and exposes a live dashboard on port 8000.

## Conventions & Patterns

- SQLite (`frigate.db`) is the primary history store; `.gitignore` excludes it.
- The package lives in `src/backend/frigate_scanner/`; `run.py` is the CLI shim.
- `uv run` handles the venv — no manual `pip install` or `source .venv/bin/activate`.
