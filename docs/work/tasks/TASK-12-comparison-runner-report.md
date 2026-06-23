# TASK-12: Comparison runner + invariant matrix + report

**State:** ready · **Model:** sonnet
**Owns (files):** `harness/run.py` (new), `harness/test_run.py` (new),
`reports/comparison.md` (new, generated artifact), `reports/README.md` (may append a "How to regenerate" note)
**Parallel-safe:** no — it is the join point of the whole spike (reads every model, the harness MATRIX, the
metrics module, and the scenario builders). All four owned files are new/append-only and disjoint from any
other task, but it must run *after* its deps and nothing else should be in flight that changes a model or scenario.
**Depends on:** 02 (mhr_replica) ✅, 03 (ridge_massey) ✅, 05 (tiers/frozen window) ✅, 06 (trend/recency) ✅,
07 (invariant harness MATRIX) ✅, 10 (truth-scoring metrics) ✅ — all `done`.
**Branch from:** latest `main` (`41ee845`) — the `/task 12` loop handles branch + PR.

---

## Goal

Build the **decision artifact** for the spike. `harness/run.py` is a model-agnostic comparison runner that
(1) runs the I1–I13 invariant checks across every model to produce a **pass/fail matrix** (the comparative
story: bespoke holds, benchmarks break), and (2) runs every model over the §7 scenario datasets and scores
each against planted truth via `harness/metrics.score_model` to produce **rank-recovery tables**. It then
renders a human-readable Markdown report to `reports/comparison.md` containing the matrix, the rank-recovery
tables, a **gate verdict**, and one **per-game attribution example "a hockey parent can read."**

This is Phase 6 of `docs/planning/PLAN.md` ("Run, review, decide") and produces the evidence the gate needs:
*bespoke passes every I1–I13 and beats the MHR replica on Stage-A rank recovery.*

---

## Read first (in this order — a cold chat must absorb all of these)

1. **`CLAUDE.md`** — prime directive (100% AI-authored, reviewed in chat), the **gate** ("must pass all
   invariants I1–I13 and beat the MHR replica on rank-recovery"), determinism is sacred (I8 — see the
   determinism decision below), observed-vs-derived wall (the runner only *consumes* `RateResult` +
   planted truth; it never feeds a score back into a solve).
2. **`docs/planning/operating-model.md`** — task template, **sonnet** model rule, trunk + PR loop, the
   "stop before merge" gate.
3. **`docs/planning/PLAN.md`** Phase 6 ("Run, review, decide") and the "Definition of done for the spike"
   list — items 2 (passes invariants on scenarios) and 3 (beats MHR on rank recovery) are what this report
   evidences. The decision output is described there: "a short report naming the model + parameterization,
   with a per-game attribution example a hockey parent can read, and the evidence."
4. **`docs/analysis/decision-memo.md`** §10 (invariant → mechanism map) and §11 Q1 (the **α caveat**) — the
   report's "Caveats / open items" section must surface that end-to-end I6 at the *reachable* gap is
   TASK-13's re-derivation, not settled here.
5. **`harness/test_harness.py`** — the **`MATRIX`** list `(inv_id, check_fn, model_name, model_fn, games_fn,
   expect)` and its `make_*_games()` factories. This is the single source of truth for the invariant matrix;
   import `MATRIX` and re-execute each cell live — do **not** re-encode pass/xfail/skip anywhere.
6. **`harness/invariants.py`** — the `check_I*` signatures `(model_fn, games) -> None` (raise `AssertionError`
   on violation). The runner calls these exactly as `test_harness.py` does.
7. **`harness/adapters.py`** — the four adapters `bespoke_flat`, `bespoke_weekly`, `mhr`, `ridge`
   (`ModelFn = (list[GameRow]) -> RateResult`). The matrix uses whichever bespoke adapter the MATRIX row
   names; the **rank-recovery** pass uses `bespoke_weekly` (the full tier+trend candidate), `mhr`, `ridge`.
8. **`harness/metrics.py`** — `score_model(ground_truth: list[TeamParams], result: RateResult) ->
   MetricsResult(spearman_rho, centered_rmse, tier_accuracy, n_teams, n_tiers_scored)`. One call per
   (model, scenario). Already handles benchmarks with empty tiers (`n_tiers_scored=0`).
9. **`scenarios/builders.py`** — the 13 `build_sNN(...) -> (Dataset, dict)` builders. `Dataset.games`
   (Level-0 rows) feed the model; `Dataset.ground_truth: list[TeamParams]` feeds `score_model`. The metadata
   dict carries `"invariants": [...]` per scenario (informational for the report).
10. **`generator/simulate.py`** — `TeamParams(.id, .attack, .defense, .tier, .trajectory)`, `.rating =
    attack − defense`; `Dataset(.games, .ground_truth)`.
11. **`models/bespoke.py`** — `RateResult` + `CreditBreakdown` (`.base, .margin_adj, .schedule_term, .w,
    .total`) for the attribution example; `rate_weekly` defaults (α via `BespokeParams`, `rho=0.2`,
    `rho_tier=0.2`, `max_window=4`) — name the parameterization in the report.

---

## Architecture decisions (settled — do not re-debate)

**The matrix is computed live from the harness `MATRIX`, never transcribed.** Import `MATRIX` from
`harness.test_harness` and, for each cell, execute `check_fn(model_fn, games_fn())` and record the *observed*
outcome. Collapse `bespoke_flat`/`bespoke_weekly` into a single **"bespoke"** column (each invariant names
exactly one bespoke adapter in the MATRIX). The three report columns are **bespoke | mhr | ridge**, rows
**I1…I13**. Cell glyphs from (expect, observed):
- `expect="pass"` and check raises nothing → **✓** (pass). If it raises → **✗ FAIL** (a real regression; the
  gate fails).
- `expect="xfail"` and check raises `AssertionError` → **✗** (documented violation — the comparative story).
  If it does *not* raise → **XPASS** (surface loudly; gate fails — the MATRIX is stale).
- `expect="skip"` → **—** (model lacks the feature, e.g. no attribution/tiers; not a failure).

**Two halves, cleanly separated.** The **invariant matrix** comes from the harness minimal constructions
(model-agnostic, the comparative story). **Rank recovery** comes from the §7 scenario datasets scored by
`score_model`. Do not try to re-derive α or tune anything — that is TASK-13. The runner reports results at
the models' **current default parameters** and names them.

**Rank-recovery aggregation excludes degenerate-truth scenarios.** Some scenarios have all-equal true
ratings by construction (e.g. S08 tie handling, S10 transitivity trap — and others where only 2–3 teams carry
signal), so Spearman ρ is undefined/meaningless there. Compute per-scenario metrics for **all 13** and show
them, but compute the **headline mean Spearman** (the "beats MHR" number) only over scenarios whose
`ground_truth` ratings have **≥ 2 distinct values with non-trivial spread** (treat a scenario as scorable when
`numpy.std(true_ratings) > 1e-9` over its teams). **`log`/note in the report which scenarios were excluded
and why** — no silent truncation. Use `bespoke_weekly` as the bespoke candidate for this pass.

**Determinism is part of the deliverable (I8 ethos).** `reports/comparison.md` must regenerate
**byte-identically** given the same code — it is a committed, diffable artifact. Therefore: **no wall-clock
timestamp, no `Date.now()`-style content, stable sort everywhere** (teams by id, scenarios by number,
invariants I1→I13, models bespoke→mhr→ridge), and round all floats to a fixed precision (e.g. `f"{x:.4f}"`).
A test asserts re-running `build_report(...)` twice yields identical strings.

**The gate verdict is computed, not asserted by prose.** `gate_verdict(...)` returns a small structured
result: `bespoke_all_invariants_pass: bool` (every bespoke cell with `expect="pass"` observed ✓, and no
benchmark XPASS) **and** `bespoke_beats_mhr: bool` (mean scorable Spearman bespoke > mhr). The report prints
**PASS/FAIL** for each half and an overall line. The end-to-end I6 α caveat (memo §11 Q1, board note) is
called out in "Caveats / open items" so the verdict is not overstated.

**Attribution example.** Pick one readable team from one scenario (recommended: **`T_SUBJECT`** from
`build_s07_close_vs_tier` — its two planted games, a close loss to the elite and a close win over the bottom,
are the I6 story in miniature). Run `bespoke_weekly` on that scenario and render `T_SUBJECT`'s
`per_game_attribution` as a small table: one row per game with `base`, `margin_adj`, `schedule_term`, weight
`w`, and `total`, plus the reconciled season rating. Prose: one or two plain-English sentences a hockey
parent could follow ("a narrow loss to the league's best counts for more than a narrow win over the worst").

**Public surface of `harness/run.py` (the testable seams).**
```python
def run_invariant_matrix() -> dict[str, dict[str, str]]:
    """{inv_id: {model_col: glyph}} where model_col in {'bespoke','mhr','ridge'} and
    glyph in {'✓','✗','—','XPASS','✗ FAIL'}. Computed live from harness.test_harness.MATRIX."""

def run_rank_recovery() -> dict[str, dict[str, MetricsResult]]:
    """{scenario_id: {model_name: MetricsResult}} over all 13 build_sNN datasets,
    models = bespoke_weekly, mhr, ridge."""

def gate_verdict(matrix: dict, recovery: dict) -> GateResult:
    """GateResult(bespoke_all_invariants_pass, bespoke_beats_mhr, mean_spearman: dict[str,float],
    scored_scenarios: list[str], excluded_scenarios: list[str])."""

def build_report(matrix: dict, recovery: dict, verdict: GateResult) -> str:
    """Deterministic Markdown string. No timestamp; stable order; fixed float precision."""

def main() -> None:
    """Wire the four together and write reports/comparison.md."""
```
`MetricsResult` and `GateResult` are imported/defined as frozen dataclasses (reuse `metrics.MetricsResult`;
define `GateResult` locally in `run.py`).

---

## TDD approach — write the tests first, watch them fail

### Step 1 — `harness/test_run.py` (all new)

Plain `def test_*` pytest functions; build inputs by calling the runner's own functions (they are pure).

```python
# test_invariant_matrix_shape:
#   m = run_invariant_matrix()
#   Assert set(m) == {f"I{i}" for i in range(1,14)} and every row has keys {'bespoke','mhr','ridge'}.

# test_bespoke_passes_every_invariant:
#   m = run_invariant_matrix()
#   For every inv, m[inv]['bespoke'] == '✓'  (this is the core gate — bespoke holds I1–I13).

# test_benchmarks_show_documented_violations:
#   m = run_invariant_matrix()
#   m['I1']['mhr'] == '✗' and m['I1']['ridge'] == '✗'   (documented I1 violations, not XPASS/FAIL).
#   No cell anywhere equals 'XPASS' or '✗ FAIL' (no regressions, no stale MATRIX).

# test_rank_recovery_covers_all_scenarios:
#   r = run_rank_recovery()
#   Assert len(r) == 13 and each value has keys for the three model names; each is a MetricsResult.

# test_gate_verdict_bespoke_wins:
#   v = gate_verdict(run_invariant_matrix(), run_rank_recovery())
#   Assert v.bespoke_all_invariants_pass is True
#   Assert v.bespoke_beats_mhr is True   (mean scorable Spearman: bespoke > mhr)
#   Assert v.excluded_scenarios is non-empty and documented (degenerate-truth scenarios listed).

# test_report_is_deterministic:
#   matrix, recovery = run_invariant_matrix(), run_rank_recovery()
#   v = gate_verdict(matrix, recovery)
#   Assert build_report(matrix, recovery, v) == build_report(matrix, recovery, v)  (byte-identical)
#   Assert 'PASS' in the report and the attribution example header (e.g. 'T_SUBJECT') is present.
```

### Step 2 — implement `harness/run.py` to green

1. `run_invariant_matrix()` — import `MATRIX`; for each cell run `check_fn(model_fn, games_fn())` inside
   try/except; map (expect, raised?) → glyph; merge bespoke_flat/weekly into the 'bespoke' column.
2. `run_rank_recovery()` — for each `build_sNN`, get `(dataset, _meta)`; for each of bespoke_weekly/mhr/ridge
   run the adapter on `dataset.games` and call `score_model(dataset.ground_truth, result)`.
3. `gate_verdict(...)` — compute the two booleans + per-model mean Spearman over scorable scenarios
   (`numpy.std(true_ratings) > 1e-9`); record scored/excluded scenario ids.
4. `build_report(...)` — assemble Markdown: title + parameterization line; invariant matrix table; per-scenario
   rank-recovery table (ρ / centered RMSE / tier-acc per model); headline mean-Spearman line + gate verdict
   (PASS/FAIL per half + overall); the `T_SUBJECT` attribution table + plain-English gloss; a
   "Caveats / open items" section (α / end-to-end I6 → TASK-13, per memo §11 Q1 and BOARD note).
   Deterministic: no timestamp, stable sort, fixed float precision.
5. `main()` — write `reports/comparison.md` (use the repo-root-relative path; create via `open(...,'w')`).

Run `pytest harness/ -q` (no regressions in `test_harness.py`/`test_metrics.py`) and `ruff check .`. Then run
`python -m harness.run` and confirm `reports/comparison.md` is written; commit it as the decision artifact.

---

## Acceptance / Definition of done

- [ ] `harness/test_run.py` — all tests above green.
- [ ] `harness/run.py` — `run_invariant_matrix`, `run_rank_recovery`, `gate_verdict`, `build_report`, `main`
      all importable; `run.py` imports `MATRIX` from `harness.test_harness` (matrix computed live, not transcribed).
- [ ] `reports/comparison.md` — generated, committed, and **byte-identical on re-run** (determinism test green);
      contains the I1–I13 × {bespoke,mhr,ridge} matrix, per-scenario rank-recovery table, headline mean-Spearman,
      the PASS/FAIL gate verdict, the `T_SUBJECT` attribution example, and the α/I6 caveat.
- [ ] `pytest -q` — full suite green (no regressions anywhere).
- [ ] `ruff check .` clean.
- [ ] **`spec-keeper`** run on the diff — confirm the runner respects the observed-vs-derived wall (only
      consumes `RateResult` + planted truth), introduces no nondeterminism, and does not double-count opponent
      strength or re-tune the floor. (No `invariant-auditor` needed: `run.py` writes no model logic — it
      *re-runs* the existing `check_I*` functions, which are the audited surface.)
- [ ] PR body: plain-English summary — what the matrix shows (bespoke ✓ across I1–I13; where mhr/ridge break),
      the headline rank-recovery numbers (bespoke vs mhr mean Spearman, scored-scenario count), the gate verdict,
      and a note that determinism of the artifact is enforced by test. Reference the α/I6 caveat as TASK-13's scope.

---

## Out of scope

- **Any model, generator, scenario, metric, or harness-check change.** This task only *orchestrates and
  reports*; if a model looks wrong, file it — don't fix it here (TASK-13 owns `models/bespoke.py`).
- **Parameter tuning / α re-derivation** — TASK-13. The report runs at current defaults and names them.
- **End-to-end I6 (S07) param sweep** — TASK-13. Surface it as a caveat only (memo §11 Q1).
- **Stage B** (walk-forward/log-loss/calibration) — out of scope for the whole spike.
- **Margin-Elo / Poisson-as-rater** benchmarks — deferred unless the decision is close (PLAN Phase 4).
- **Charts/plots or HTML** — Markdown tables only; a hosted demo UI is a later phase, not this task.
