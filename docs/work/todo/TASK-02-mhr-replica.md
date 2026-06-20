# TASK-02: MHR replica benchmark

**Status:** todo
**Model:** sonnet — standard implementation from a clear spec, tests as guardrails.
**Parallel-safe:** yes — new file `models/mhr_replica.py` + its tests only. Safe to run alongside TASK-01/03/04.
**Depends on:** the `RateResult` interface (done). **Branch from:** `f4c5895`.

## Goal
Implement the incumbent we're trying to beat, behind the common interface, so "better" is measured not
asserted (brief §3.1). This is a **benchmark — it is allowed (expected) to fail some invariants** (notably
I1 result-ordering, which MHR violates; that's the whole motivation). Document which it fails.

## Read first
- `CLAUDE.md`, `docs/planning/operating-model.md`, this file.
- `docs/knowledge-bank/rating-model-test-brief.md` §3.1 (MHR replica spec) and §212 (context: ±7 cap).
- `models/bespoke.py` — copy the `RateResult` shape and the `rate(games, ...) -> RateResult` signature
  and the deterministic patterns (sorted teams, canonical summation, centering). Reuse `core` Level-0/1.

## Approach (TDD)
MHR-style iterative solve: each team rating = **AGD** (average goal differential per game, each game's GD
**capped at ±7**) + **SCHED** (mean of opponents' current ratings), iterated to convergence. Deterministic
(no RNG, stable order, fixed tolerance). Center ratings to mean 0.
- Test: determinism + order-independence (mirror I8 from `test_bespoke_rate.py`).
- Test: converges; recovers gross order on a generator round-robin (weaker than bespoke is fine).
- Test (documentation): construct a case where MHR **violates I1** (a bigger-margin win/regime where result
  ordering flips) and assert the replica reproduces that flaw — this is the comparative story.

## Acceptance / Definition of done
- [ ] `rate()` conforms to `RateResult`; deterministic; full `pytest` green; `ruff check .` clean.
- [ ] A short docstring/comment listing which §4 invariants it fails and why.
- [ ] Commit in house style; move to `docs/work/done/`; update `README.md`.

## Out of scope
Do not modify `models/bespoke.py` or shared `core`. No tier/trend features — straight AGD+SCHED.
