# Work queue — remaining spike tasks

Map of remaining work to reach v1 (the bespoke model passes all §4 invariants on §7 scenarios and beats
the MHR replica on Stage-A rank recovery). See `docs/planning/operating-model.md` for the task format,
model matching, and parallelization rules. Branch each task from the noted commit.

## Status snapshot (as of f4c5895)
Done: data contract (L0/L1), generator core, bespoke credit floor **I1–I5**, solve **I8/I9** + recovery.
Remaining below.

## Dependency & parallel groups

```
CRITICAL PATH (opus, sequential, one chat — touches models/bespoke.py):
  TASK-01 cross-opponent invariants (I6, I7, I10, I12)
        |
  TASK-05 tiers + frozen window (I13)  ──┐
  TASK-06 trend + recency (I11)          │ (can follow 01; 05 & 06 are largely independent of each other)
        |                                │
  TASK-07 generalize invariant harness (model-agnostic I1–I13 runner)  [needs ≥1 model + invariants]

PARALLEL GROUP A — benchmark models (sonnet, independent files, run concurrently):
  TASK-02 mhr_replica       TASK-03 ridge_massey        (each its own models/<name>.py)

PARALLEL GROUP B — generator features (sonnet, independent, concurrent with everything):
  TASK-04 multi-week trajectories   TASK-08 Dixon–Coles correction   TASK-09 §8 JSON serialization

LATER (depend on the above):
  TASK-10 truth-scoring metrics (Spearman/Kendall, centered RMSE/MAE, tier accuracy)  [sonnet]
  TASK-11 scenario suite §7 (needs TASK-04 for trajectories)                          [sonnet, parallel per scenario]
  TASK-12 comparison runner + invariant matrix + rank-recovery report                 [sonnet; needs all models + harness]
  TASK-13 Stage-A tuning of strawman params toward rank recovery                      [opus; needs 11+12]
```

## Recommended order
1. **TASK-01** now (critical path, this finishes the core fairness story).
2. In parallel with 01: **Group A** (benchmarks) and **Group B** (generator) — independent, sonnet, safe to fan out.
3. Then TASK-05/06, TASK-07, TASK-10.
4. Then TASK-11 (scenarios) → TASK-12 (report) → TASK-13 (tune) → **v1 decision**.

## Task files
- [TASK-01](TASK-01-cross-opponent-invariants.md) — cross-opponent invariants (opus, sequential)
- [TASK-02](TASK-02-mhr-replica.md) — MHR replica benchmark (sonnet, parallel-safe)
- [TASK-03](TASK-03-ridge-massey.md) — ridge Massey benchmark (sonnet, parallel-safe)
- [TASK-04](TASK-04-generator-trajectories.md) — multi-week trajectories (sonnet, parallel-safe)
- Not-yet-written (capture when ready): TASK-05/06/07/08/09/10/11/12/13 — specs sketched above; expand
  into full files from the operating-model template before handing off.
