# Work Board — single source of truth for task state

The **only** place task state lives. On `master`/`main`. Task files are in `docs/work/tasks/`.
See `docs/planning/operating-model.md` for how tasks flow. Start one with `/task <id>`; see this with `/board`.

**Lifecycle:** `backlog` (idea) → `refined` (task file complete) → `ready` (refined + deps done) →
`in-progress` (branch open) → `in-review` (PR open) → `done`. (`blocked` if a dep regresses.)

**Parallel rule:** two tasks may run concurrently only if their **Owns (files)** sets are disjoint.
Anything owning `models/bespoke.py` is **sequential** — never run two of those at once.

## ▶ Ready now

- **TASK-10** truth-scoring metrics — sonnet — `harness/metrics.py` + `harness/test_metrics.py` — critical path (blocks 12)

~~**TASK-08** Dixon–Coles low-score correction — sonnet~~ (done)
~~**TASK-09** JSON serialization — haiku~~ (done)

**Sequential core-model chain (own `models/bespoke.py`):** 05 ✅ → 06 ✅ → **13 (next)**. 13 is blocked on 11 + 12; never parallelize the chain.

## Board

| ID | Title | State | Model | Owns (files) | Parallel | Deps |
|----|-------|-------|-------|--------------|----------|------|
| 01 | Cross-opponent invariants (I6/I7/I10/I12) | **done** | opus | models/bespoke.py | no (core) | — |
| 02 | MHR replica benchmark | **done** | sonnet | models/mhr_replica.py | yes | — |
| 03 | Ridge Massey benchmark | **done** | sonnet | models/ridge_massey.py | yes | — |
| 04 | Generator multi-week trajectories | **done** | sonnet | generator/* | yes | — |
| 05 | Tiers + frozen window (I13) | **done** | opus | models/bespoke.py, models/tiers.py | **no (core)** | 01 |
| 06 | Trend + recency weighting (I11) | **done** | opus | models/bespoke.py, models/test_bespoke_rate.py, models/test_bespoke_trend.py | **no (core)** | 01,05 |
| 07 | Model-agnostic invariant harness (I1–I13 runner) | **done** | sonnet | harness/* | yes | 01,02 |
| 08 | Dixon–Coles low-score correction | **done** | sonnet | generator/world.py | no (vs 04) | 04 |
| 09 | §8 JSON serialization (dataset ↔ json) | **done** | haiku | generator/io.py | yes | — |
| 10 | Truth-scoring metrics (Spearman/RMSE/tier acc) | **in-review** | sonnet | harness/metrics.py, harness/test_metrics.py | yes | — |
| 11 | Scenario suite §7 | **done** | sonnet | scenarios/* | yes (per scenario) | 04 |
| 12 | Comparison runner + invariant matrix + report | backlog | sonnet | reports/*, harness/run.py | no | 02,03,05,06,07,10 |
| 13 | Stage-A tuning of strawman params | backlog | opus | models/bespoke.py | no (core) | 11,12 |

## Notes
- **Sequential chain on the model core** (own `models/bespoke.py`): 05 ✅ → 06 ✅ → 13. Never parallelize these.
- 08 depends on 04 (both touch `generator/world.py`) → run after 04 merges, not beside it.
- To refine a backlog item into a full task file: `/task-new <id or description>` (writes
  `docs/work/tasks/TASK-NN-*.md` from the template, flips the row to `refined`).
- The integration (merge) step flips a row to `done`; the task's own loop flips it to `in-progress`/`in-review`.
- **α finding (from TASK-11 Scenario 7):** At the solver's reachable spread (R_TOP − R_BOTTOM ≈ 4.38), I6
  requires α ≥ 0.69 (not 0.60). At α=0.8 it passes. TASK-13 must re-derive α against the reachable gap
  before locking the strawman params. See `scenarios/test_s07_close_vs_tier.py` for the exact values.
- **Scenario 13 / freeze-window damping:** At `rho_tier=0.2`, windowed damping is structural but modest
  (~1.7% swing reduction, window=1 → window=4). The directional assertion holds; the 50% bound from the
  task spec assumes sharper `rho_tier`. TASK-13 may revisit if stronger damping is needed.
