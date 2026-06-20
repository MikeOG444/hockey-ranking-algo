---
description: Show the work board — what's ready to pick up next, plus in-flight tasks
---

Read `docs/work/BOARD.md` and report concisely:

1. **▶ Ready now** — the pick-up-next queue (refined + deps met). For each: id, title, model, and whether
   it's parallel-safe. Call out any valid **parallel batch** (≥2 ready tasks with disjoint **Owns** files).
2. **In flight** — any rows in `in-progress` / `in-review`. Cross-check with `git branch` and
   `gh pr list` (if a remote exists) so the board matches reality; flag drift.
3. **Blocked / backlog** — one line on what's next to refine (`/task-new`) and what it's waiting on.

Keep it short — this is a status glance, not a full read-out. Do not modify anything.
