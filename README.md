# Hockey Rating Model — Research Spike

A transparent, explainable, deterministic, fair youth-hockey rating model that fixes the failures we
dislike in MyHockey Rankings (ugly-win punishment, stale-schedule effects, over-rewarded ties) — without
crippling the margin and schedule signal.

**Status:** research spike. Goal = *identify the correct model* against synthetic ground truth (Stage A).
Productionalization (real-data backtest, hosting, the public demo) comes after the model is chosen.

> Context: USA 11U AAA, 2025–26. Sample / non-commercial.

## How this repo is organized

| Path | Purpose |
|---|---|
| `docs/planning/` | Execution plan, scope, sequencing. **Start at [`docs/planning/PLAN.md`](docs/planning/PLAN.md).** |
| `docs/analysis/` | Design decisions & math. **[`decision-memo.md`](docs/analysis/decision-memo.md) is the Phase-0 gate.** |
| `docs/implementation/` | Build notes, interface contracts, per-module design as code lands. |
| `docs/knowledge-bank/` | Reference: the brief, observed tier data, source facts. |
| `docs/work/` | **[`BOARD.md`](docs/work/BOARD.md)** = live task state (source of truth); `tasks/` = task files. |
| `generator/` | Synthetic Dixon–Coles world model + scenario configs (seeded) → `data/*.json`. |
| `models/` | Candidate raters behind one interface: `mhr_replica`, `ridge_massey`, `bespoke`. |
| `harness/` | Invariant checks (I1–I13), truth-scoring, calibration. |
| `scenarios/` | §7 edge-case configs + expected assertions. |
| `data/` | Generated test JSON (synthetic ground truth). Gitignored if large. |
| `reports/` | Per-run results, comparison tables, invariant pass/fail matrix. |

## The method (non-negotiable)

**Design the tests first; let them define the model.** Build bottom-up:
data contract → generator → invariants-as-tests → models → run → review.
We tune the model until the invariants hold and rank-recovery is strong — never to flatter a result.

## Stack
Python (numpy/scipy/pandas, pytest). The winning model gets ported to TypeScript during productionalization.

## Status & how we work
Live task state — done / in-flight / **ready to pick up next** — lives on the board, not here (status prose
churns and causes merge conflicts):

➡ **[`docs/work/BOARD.md`](docs/work/BOARD.md)**

How tasks are sliced, matched to a model, run on trunk, and (when safe) parallelized:
**[`docs/planning/operating-model.md`](docs/planning/operating-model.md)**. Phase arc and scope:
[`docs/planning/PLAN.md`](docs/planning/PLAN.md).

High-level: data contract ✓ → generator ✓ → bespoke model (passing the §4 invariants; I1–I10/I12 done,
I11/I13 next) → benchmarks (MHR ✓) → scenarios → pick the model.
