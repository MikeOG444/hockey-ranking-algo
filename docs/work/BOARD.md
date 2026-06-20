# Work Board — single source of truth for task state

The **only** place task state lives. On `master`/`main`. Task files are in `docs/work/tasks/`.
See `docs/planning/operating-model.md` for how tasks flow. Start one with `/task <id>`; see this with `/board`.

**Lifecycle:** `backlog` (idea) → `refined` (task file complete) → `ready` (refined + deps done) →
`in-progress` (branch open) → `in-review` (PR open) → `done`. (`blocked` if a dep regresses.)

**Parallel rule:** two tasks may run concurrently only if their **Owns (files)** sets are disjoint.
Anything owning `models/bespoke.py` is **sequential** — never run two of those at once.

## ▶ Ready now (refined + deps met — pick from here)
- **TASK-03** ridge Massey benchmark — sonnet — parallel-safe (own files)
- **TASK-04** generator trajectories — sonnet — parallel-safe (own files)

> TASK-03 + TASK-04 own disjoint files → valid **parallel batch** (orchestrator or two chats).

## Board

| ID | Title | State | Model | Owns (files) | Parallel | Deps |
|----|-------|-------|-------|--------------|----------|------|
| 01 | Cross-opponent invariants (I6/I7/I10/I12) | **done** | opus | models/bespoke.py | no (core) | — |
| 02 | MHR replica benchmark | **done** | sonnet | models/mhr_replica.py | yes | — |
| 03 | Ridge Massey benchmark | **done** | sonnet | models/ridge_massey.py | yes | — |
| 04 | Generator multi-week trajectories | **done** | sonnet | generator/* | yes | — |
| 05 | Tiers + frozen window (I13) | backlog | opus | models/bespoke.py, models/tiers.py | **no (core)** | 01 |
| 06 | Trend + recency weighting (I11) | backlog | opus | models/bespoke.py | **no (core)** | 01 |
| 07 | Model-agnostic invariant harness (I1–I13 runner) | backlog | sonnet | harness/* | yes | 01,02 |
| 08 | Dixon–Coles low-score correction | backlog | sonnet | generator/world.py | no (vs 04) | 04 |
| 09 | §8 JSON serialization (dataset ↔ json) | backlog | haiku | generator/io.py | yes | — |
| 10 | Truth-scoring metrics (Spearman/RMSE/tier acc) | backlog | sonnet | harness/metrics.py | yes | — |
| 11 | Scenario suite §7 | backlog | sonnet | scenarios/* | yes (per scenario) | 04 |
| 12 | Comparison runner + invariant matrix + report | backlog | sonnet | reports/*, harness/run.py | no | 02,03,05,06,07,10 |
| 13 | Stage-A tuning of strawman params | backlog | opus | models/bespoke.py | no (core) | 11,12 |

## Notes
- **Sequential chain on the model core** (own `models/bespoke.py`): 05 → 06 → 13. Never parallelize these.
- 08 depends on 04 (both touch `generator/world.py`) → run after 04 merges, not beside it.
- To refine a backlog item into a full task file: `/task-new <id or description>` (writes
  `docs/work/tasks/TASK-NN-*.md` from the template, flips the row to `refined`).
- The integration (merge) step flips a row to `done`; the task's own loop flips it to `in-progress`/`in-review`.
