# Work Board — single source of truth for task state

The **only** place task state lives. On `master`/`main`. Task files are in `docs/work/tasks/`.
See `docs/planning/operating-model.md` for how tasks flow. Start one with `/task <id>`; see this with `/board`.

**Lifecycle:** `backlog` (idea) → `refined` (task file complete) → `ready` (refined + deps done) →
`in-progress` (branch open) → `in-review` (PR open) → `done`. (`blocked` if a dep regresses.)

**Parallel rule:** two tasks may run concurrently only if their **Owns (files)** sets are disjoint.
Anything owning `models/bespoke.py` is **sequential** — never run two of those at once.

## ▶ Ready now

**TASK-15** real MHR data loader + data-quality report — sonnet. Convert the external top-50 per-team JSON
dump (USA 11U AAA 2025–26) into one §8 Level-0 dataset the existing raters can consume, plus a generated
quality report. Core job is a **validated dedup**: games are listed per-team, so the 1,044 intra-top-50
matchups each appear twice (mirror-checked: 0 score mismatches) while 1,086 games vs outside teams appear
once → **2,130 unique games**. Also derives the two missing Level-0 fields — **week** (week 1 ≤ 2025-09-09,
then Wed→Tue buckets) and a **year** on the bare date (Aug–Dec→2025, Jan–Jul→2026). **Keeps** the 215
outside-top-50 opponents for schedule strength. **Purely additive** — new `ingest/` package + `data/real/`
+ a new report; touches no model/generator/harness/scenario, so **parallel-safe** with anything. Runs
**no model and no accuracy metric** (real data has no planted truth — the comparison yardstick is a
deliberate follow-up). No deps. First **Stage-B** step (formally a scope expansion past the synthetic spike).

~~**TASK-14** point-in-time truth for trajectory scenarios — sonnet.~~ (done, #12)

~~**TASK-10** truth-scoring metrics — sonnet~~ (done)

~~**TASK-08** Dixon–Coles low-score correction — sonnet~~ (done)
~~**TASK-09** JSON serialization — haiku~~ (done)

~~**TASK-12** comparison runner + invariant matrix + report — sonnet~~ (done, #10). Decision artifact written to `reports/comparison.md`: bespoke holds all I1–I13, but at current defaults does **not** yet beat MHR on mean Spearman (0.6811 vs 0.7769) — accuracy is now TASK-13's explicit tuning target.

~~**TASK-13** Stage-A tuning of strawman params — opus~~ (done, #11). α re-derived against the
reachable gap (≈4.38) and shipped at **0.75** — the deliberately-red S07/I6 test is now green end-to-end,
and α=0.75 is the argmax of the deterministic `harness/tune.py` rank-recovery sweep. **Honest-fallback
outcome:** within the invariant-safe region bespoke improves (mean Spearman 0.6811 → 0.6928) but does
**not** beat MHR (0.7769); the gate reads **FAIL** honestly. Residual diagnosed as (1) the S04/S11
trajectory measurement artifact and (2) the structural fairness-floor cost on S05 (giant-killer) — no
cherry-picking. **Recommended follow-up:** a new task to score trajectory scenarios (S04/S11) against
point-in-time truth in `harness/metrics.py`/`scenarios` (removes the measurement artifact; the structural
S05 gap is a deliberate cost of the fairness floor and stays).

**Sequential core-model chain (own `models/bespoke.py`):** 05 ✅ → 06 ✅ → 13 ✅ — chain complete.

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
| 10 | Truth-scoring metrics (Spearman/RMSE/tier acc) | **done** | sonnet | harness/metrics.py, harness/test_metrics.py | yes | — |
| 11 | Scenario suite §7 | **done** | sonnet | scenarios/* | yes (per scenario) | 04 |
| 12 | Comparison runner + invariant matrix + report | **done** | sonnet | reports/*, harness/run.py, harness/test_run.py | no | 02,03,05,06,07,10 |
| 13 | Stage-A tuning of strawman params | **done** | opus | models/bespoke.py, models/test_bespoke_tuning.py, harness/tune.py, harness/test_tune.py, reports/comparison.md | no (core) | 11,12 |
| 14 | Point-in-time truth for trajectory scenarios | **done** | sonnet | harness/metrics.py, harness/test_metrics.py, harness/run.py, harness/test_run.py, reports/comparison.md | no (re-scores all) | 10,11,12,13 |
| 15 | Real MHR data loader + data-quality report | **done** | sonnet | ingest/* (new), data/real/* (new), reports/real-data-quality.md (new) | yes (additive) | — |
| 16 | Head-to-head agreement + giant-killer case studies (real) | **done** | sonnet | analysis/* (new), reports/real-h2h.md (new) | yes (after 15) | 15 |
| 17 | Resolve the closing-schedule floor cost (opponent-aware recency + floor/schedule) | **ready** | opus | models/bespoke.py, models/test_bespoke_*.py, scenarios/test_s14_closing_schedule.py, reports/comparison.md | no (core) | 15, 16 |

## Notes
- **Sequential chain on the model core** (own `models/bespoke.py`): 05 ✅ → 06 ✅ → 13. Never parallelize these.
- 08 depends on 04 (both touch `generator/world.py`) → run after 04 merges, not beside it.
- To refine a backlog item into a full task file: `/task-new <id or description>` (writes
  `docs/work/tasks/TASK-NN-*.md` from the template, flips the row to `refined`).
- The integration (merge) step flips a row to `done`; the task's own loop flips it to `in-progress`/`in-review`.
- **α finding — RESOLVED (TASK-13):** At the solver's reachable spread (R_TOP − R_BOTTOM ≈ 4.38), end-to-end
  I6 requires α ≳ 0.69 (not 0.60). α is now re-derived and shipped at **0.75** — the sweep argmax
  (`harness/tune.py`) that also clears I6 with margin and keeps the I9 contraction (α(1−λ)=0.71). The
  formerly-red `scenarios/test_s07_close_vs_tier.py` is green at the shipped default.
- **Scenario 13 / freeze-window damping:** At `rho_tier=0.2`, windowed damping is structural but modest
  (~1.7% swing reduction, window=1 → window=4). The directional assertion holds; the 50% bound from the
  task spec assumes sharper `rho_tier`. TASK-13 may revisit if stronger damping is needed.
- **Stage-B begins at TASK-15.** The synthetic spike is complete (fairness solved I1–I13; accuracy a near-tie
  vs the MHR replica — the one residual loss, S05/giant-killer, is exactly where real MHR is itself fooled by
  schedule padding, e.g. Dallas Stars Elite #12 on a 7-9-1 ranked record). Full phased arc:
  **[`docs/planning/stage-b-plan.md`](../planning/stage-b-plan.md)** (B1 data → B2 head-to-head/case studies
  → B3 prediction surface → B4 walk-forward → B5 prediction metrics → B6 trust layer → B7 demo). TASK-15 = B1;
  TASK-16 = B2. The non-obvious gate is **B3**: bespoke emits ratings, not probabilities, and every
  prediction metric needs a probability — nothing in B4–B6 works until that link is built.
