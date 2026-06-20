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
| `docs/work/{todo,ready,done}` | Task tracking through the lifecycle. |
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

## Where we are
- [x] Plan locked — [`docs/planning/PLAN.md`](docs/planning/PLAN.md)
- [x] **Phase 0: Decision memo** drafted, all tensions resolved, 4 design decisions made — [`docs/analysis/decision-memo.md`](docs/analysis/decision-memo.md) §11
- [x] **Owner sign-off on the memo** + 4 design decisions
- [x] **Phase 1: data contract** — Level-0 `GameRow` (outcome inferred, frozen) + Level-1 aggregator (folds the log, flips perspective, never trusts a summary). 14 tests, TDD.
- [ ] Phase 2: synthetic Dixon–Coles generator (+ ground truth)
- [ ] Phase 3–6: invariant harness → models → scenarios → decide
