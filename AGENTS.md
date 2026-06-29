# Agent Guide

This file is the repo-specific workflow for AI agents. This project uses **bd (beads)** for issue tracking. Run `bd prime` for full workflow context.

## Principles

**Think before coding.** State assumptions explicitly. If uncertain, ask rather than guess. Present multiple interpretations when ambiguity exists. Push back when a simpler approach exists. Stop when confused — name what's unclear.

**Simplicity first.** Minimum code that solves the problem. Nothing speculative. No features beyond what was asked. No abstractions for single-use code. If a senior engineer would say it's overcomplicated, simplify.

**Surgical changes.** Touch only what you must. Clean up only your own mess. Don't "improve" adjacent code, comments, or formatting. Don't refactor what isn't broken. Match existing style.

**Read before you write.** Before adding code, read exports, immediate callers, and shared utilities. This is a monorepo with shared libs — check for existing shared code before writing new helpers. "Looks orthogonal" is dangerous. If unsure why code is structured a certain way, ask.

**Goal-driven execution.** Define success criteria before starting. Loop until verified. Don't follow steps blindly — define success and iterate.

**Surface conflicts, don't average them.** If two patterns contradict, pick one (more recent / more tested). Explain why. Flag the other for cleanup. Don't blend conflicting patterns.

**Tests verify intent, not just behavior.** Tests must encode WHY behavior matters. A test that can't fail when business logic changes is wrong.

**Checkpoint after every significant step.** Summarize what was done, what's verified, what's left. Don't continue from a state you can't describe back. If you lose track, stop and restate.

**Match codebase conventions, even if you disagree.** Conformance > taste. If you think a convention is harmful, surface it — don't fork silently.

**Fail loud.** "Completed" is wrong if anything was skipped silently. "Tests pass" is wrong if any were skipped. Default to surfacing uncertainty, not hiding it.

## Core Rules

* Never commit to `main`.
* Use `bd` for ALL task tracking. Do not use TodoWrite, TaskCreate, or create markdown TODO lists.
* Run `bd prime` for detailed command reference and session close protocol.
* Use `bd remember` for persistent knowledge — do not use MEMORY.md files. Read memories with `bd memories --json`.
* If a task belongs to a parent `feature` or `epic`, append durable context before closing the child:
```bash
bd update <parent_id> --append-notes "..." --json

```


* `--append-notes` takes a literal string. It does not read from stdin when passed `-`.
* Do not use `bd edit`; it is interactive. Use `bd update ...` flags instead.
* Keep changes scoped to the active issue. File follow-up `bd` issues for newly discovered work.

## Non-Interactive Shell Commands

**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts. Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**

```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest

```

**Other commands that may prompt:**

* `scp` - use `-o BatchMode=yes` for non-interactive
* `ssh` - use `-o BatchMode=yes` to fail instead of prompting
* `apt-get` - use `-y` flag
* `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var

## Start Every Task

```bash
bd memories --json
bd ready --json
bd create --title="..." --description="..." --type=task --priority=2 --json
git checkout -b issue/<id>
bd update <id> --claim --json

```

If the issue already exists, skip `bd create` and use that id.

## Beads Usage

* Prefer `--json` for all agent-facing `bd` commands.
* If you want an issue to behave like an epic in `bd list`, create it with `--type=epic`. A title like `Epic: ...` is not enough.
* Default to `task` unless the work clearly fits another type:
* `bug`: broken behavior
* `feature`: new capability
* `task`: scoped implementation, tests, docs, or refactor
* `epic`: parent issue with sub-issues
* `chore`: maintenance, tooling, or dependency work


* For epic/sub-task nesting, create children with `--parent <epic-id>` or reparent existing issues with `bd update <child-id> --parent <epic-id> --json`.
* `--deps discovered-from:<id>` records provenance only. It does not make the issue a child in the `bd list` tree.
* For text with quotes, backticks, or shell-sensitive characters, pipe via stdin:

```bash
echo 'text with `backticks` and "quotes"' | bd create "Title" --description=- --json
echo 'updated text' | bd update <id> --description=- --json

```

Epic/sub-task example that produces a nested tree in `bd list --pretty`:

```bash
bd create --title="Core system overhaul" --type=epic --priority=1 --json
bd create --title="Add initialization struct" --type=task --priority=1 --parent=<epic_id> --json
bd create --title="Add timing telemetry" --type=task --priority=1 --parent=<epic_id> --json
bd list --id <epic_id> --pretty --no-pager

```

Expected shape:

```text
○ PROJ-123 ● P1 [epic] Core system overhaul
├── ○ PROJ-123.1 ● P1 Add initialization struct
└── ○ PROJ-123.2 ● P1 Add timing telemetry

```

Notes examples:

```bash
bd update <id> --append-notes "Investigated timeout; root cause is unbounded data." --json
bd update <id> --append-notes "$(cat /tmp/issue-note.txt)" --json

```

## Session Completion, Validation & Delivery

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up.
2. **Run quality gates** (if code changed) - Run repo-standard validation:
```bash
just check

```


*(For UI-only changes, use the scripts in `apps/ui/package.json`)*
3. **Update issue status** - Close finished work, update in-progress items:
```bash
bd close <id> --reason="Completed implementation for..."

```


4. **Create Pull Request** - Ensure you use Conventional Commits and branch format `issue/<bd-id>`:
```bash
gh pr create --base main --title "issue/<id>: ..." --body "Closes bd <id>"

```



5. **Clean up** - Clear stashes, switch back to main, and prune remote branches:
```bash
git checkout main
git pull --rebase
git branch -d issue/<id>
git remote prune origin

```


6. **Verify & Hand off** - Ensure all changes are committed AND pushed. Provide context for the next session.

**CRITICAL RULES:**

* Work is NOT complete until `git push` succeeds.
* NEVER stop before pushing - that leaves work stranded locally.
* NEVER say "ready to push when you are" - YOU must push.
* If push fails, resolve and retry until it succeeds.
