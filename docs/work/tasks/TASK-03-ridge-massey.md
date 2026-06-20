# TASK-03: ridge Massey benchmark

**State:** ready · **Model:** sonnet — textbook method from a clear spec.
**Owns (files):** `models/ridge_massey.py`, `models/test_ridge_massey.py` (+ `pyproject.toml` deps only if scipy added).
**Parallel-safe:** yes (disjoint from TASK-04). **Depends on:** `RateResult` (done, on `main`).
**Branch from:** latest `main` — the `/task 03` loop handles branch + PR.

## Goal
Implement regularized least-squares on goal margins — the clean textbook analog to MHR, a transparent
benchmark with strong rank recovery (brief §3.3). A second yardstick for the bespoke model.

## Read first
- `CLAUDE.md`, `docs/planning/operating-model.md` (v2 — trunk/PR flow), this file.
- `docs/knowledge-bank/rating-model-test-brief.md` §3.3.
- `models/bespoke.py` for the `RateResult` shape + deterministic conventions. `core` for Level-0 rows.
- numpy is available; `scipy` is **not yet a dep** — if you need `lstsq`, numpy's is fine; if you add
  scipy, add it to `pyproject.toml` `dependencies` and reinstall (`pip install -e ".[dev]"`).

## Approach (TDD)
Build the Massey system: for each game, `rating_i − rating_j ≈ margin` (margin = goal diff, optionally
capped). Solve the normal equations with an L2 (ridge) penalty for a unique, stable solution on sparse/
disconnected graphs. Anchor the gauge by centering to mean 0. Fully deterministic.
- Test: determinism + order-independence.
- Test: on a generator round-robin with known truth, Spearman/rank order matches (should be strong).
- Test: ridge term yields a finite, unique solution on a disconnected 2-pod graph (no blow-up).

## Acceptance / Definition of done
- [ ] `rate()` conforms to `RateResult`; deterministic; full `pytest` green; `ruff check .` clean.
- [ ] If scipy added: `pyproject.toml` `dependencies` updated; note it in the commit.
- [ ] Commit in house style; flip the board row to `in-review`; open a PR and stop for approval.

## Out of scope
No changes to `bespoke.py` / `core`. Margins only (no bucketed credit, no tiers) — it's a benchmark.
