---
description: Execute a task from docs/work/tasks by id — full TDD loop, stop before merge (opens a PR)
argument-hint: <task-id, e.g. 03>
---

Execute task **$1**. You are the executing agent for one task, end to end, stopping before merge.

## 0. Load context
- Read `docs/work/tasks/TASK-$1-*.md` (the task spec). Read `CLAUDE.md` and `docs/planning/operating-model.md`
  if not already in context. Re-read the task's "Read first" references.
- Check `docs/work/BOARD.md`: confirm this task's **Deps** are all `done`. If a dep is not done, **STOP** and
  report the task is blocked — do not start.
- Confirm no other in-flight task **Owns** an overlapping file (esp. `models/bespoke.py`). If overlap exists,
  **STOP** and report the conflict.

## 1. Branch from latest master
- `git switch master && git pull --ff-only` (ignore pull error if no remote yet).
- Create the task branch: `git switch -c task/$1-<short-slug-from-task-title>`.
- Flip this task's row in `docs/work/BOARD.md` to **in-progress** (committed on the branch).

## 2. TDD loop (the heart — follow CLAUDE.md)
- Strictly test-first: write each failing test, **watch it fail for the right reason**, then minimal code,
  then refactor green. No production code before a failing test. Preserve determinism (I8).
- Stay inside the task's **Owns (files)** scope. Touch nothing else.
- Iterate until the task's Definition of Done is met.

## 3. Verify
- `.venv/bin/python -m pytest -q` → all green. `.venv/bin/ruff check .` → clean. Show the output.
- If the task touches a model or the fairness floor, run the **invariant-auditor** agent (and **spec-keeper**
  if it says so) and include their verdict.

## 4. Commit + PR, then STOP
- Commit in the house style (see `git log`; end with the Co-Authored-By trailer).
- Flip the BOARD row to **in-review**; commit.
- Push the branch and open a PR: `gh pr create --fill` or with an explicit title/body. The PR body must be a
  **plain-English summary a non-coder can follow** — what changed, which invariants/behaviors it satisfies,
  the test evidence — plus the DoD checklist.
- **STOP.** Do not merge. Report: the PR number/URL, a one-paragraph summary, and "Ready to merge — approve?"

If you hit a genuine design decision the task doesn't resolve (e.g. a tuning value that affects an
invariant), **stop and ask** rather than guessing.
