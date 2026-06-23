# TASK-14: Point-in-time truth for trajectory scenarios

**State:** ready · **Model:** sonnet — this is **measurement/harness** work, not model-core: it changes
how trajectory scenarios are *scored*, never the model. Clear spec + strong test guardrails (every
existing static-scenario number must stay byte-identical), so sonnet — but it does decide the spike's
headline gate, so if the gate-redefinition call below feels genuinely contested when you reach it,
**stop and step up to opus** rather than guess.
**Owns (files):** `harness/metrics.py` + `harness/test_metrics.py` (TASK-10's), `harness/run.py` +
`harness/test_run.py` (TASK-12's), `reports/comparison.md` (regenerated artifact), and — only if you add
a point-in-time scoring assertion to the §7 suite — `scenarios/test_s04_stale_opponent.py` /
`scenarios/test_s11_momentum.py` (TASK-11's).
**Must NOT touch:** `models/bespoke.py` (the model is settled — this is purely a measurement change),
`generator/*` (`week_params` is already exported — consume it, don't change it), and
`scenarios/builders.py` (no builder change is needed: trajectory lives on `TeamParams`, week count is read
from the game log).
**Parallel-safe:** **no** — it re-scores every model across every scenario and regenerates the decision
artifact (same reason TASK-13 was sequential). Nothing that changes a model, scenario, metric, the harness
MATRIX, or the report may be in flight beside it.
**Depends on:** TASK-10 (done — `score_model`/`metrics.py`), TASK-11 (done — the §7 scenario suite +
`week_params` trajectories), TASK-12 (done — `run.py`/`gate_verdict`/`build_report`/the report), TASK-13
(done — diagnosed this exact artifact and filed this follow-up). All `done`.
**Branch from:** latest `main` (`cd02def`) — the `/task 14` loop handles branch + PR.

> **Baseline before you start:** `pytest -q` should be **fully green** (TASK-13 resolved the last
> deliberately-red S07 test). Confirm that, then write the new failing tests first.

---

## Goal

The truth-scorer grades every team against its **static** planted rating (`TeamParams.rating =
attack − defense`), which for a drifting team is the season *average*. Bespoke's recency weighting (I11)
is *built* to track **current** form, so on the two trajectory scenarios it is scored **backwards** — most
starkly S11 (momentum): bespoke **−0.50** vs mhr **−0.10**, where ranking the rising team above the
falling one is the *correct current-form call* that disagrees with the season-average answer key. TASK-13
diagnosed this as a **measurement artifact, not a model defect** (see `reports/comparison.md` §4 "Cause 1"
and §6) and deferred it because the tuning task does not own the scorer or the scenarios.

This task removes the artifact by surfacing **point-in-time truth** — each team's **end-of-season realized
form**, `week_params(team, last_week).rating`, taken straight from the generator — and scoring the
**trajectory scenarios (S04, S11) against it** instead of the season average. Static scenarios are
untouched: for a `flat` team `week_params` returns the raw baseline, so their scores stay
**byte-identical**. The result is reported honestly: the comparison artifact shows S04/S11 re-scored, and
**the residual S05 (giant-killer) gap stays** — that one is a deliberate *structural* cost of the fairness
floor (I1), not a measurement choice, and is expected to remain (see §4 "Cause 2").

This is the **recommended follow-up** TASK-13 filed (BOARD ▶ Ready-now note + `reports/comparison.md` §6).

---

## Two things settled here (do not re-debate)

1. **Point-in-time truth is GROUND truth, not a recovered rating — the observed-vs-derived wall holds
   (brief §5).** The point-in-time key is computed from the generator's hidden `TeamParams` via the
   already-exported `generator.simulate.week_params`, exactly as the generator itself does when it
   simulates each week. It is *never* a model output fed back in. `week_params` is a pure function (no RNG,
   no wall-clock), so determinism (I8) is preserved and the regenerated report still hashes identically.

2. **The point-in-time target is end-of-season form (the last finalized week), and it replaces the answer
   key for trajectory scenarios in the *actual* rank-recovery + gate — not as a cosmetic side table.** A
   "current rating" is meant to reflect how good a team is *now* (end of season), which is precisely what
   I11 demands; end-of-season `week_params` is the correct truth for that question. So `run_rank_recovery`
   scores S04/S11 against point-in-time truth and the headline gate reads that corrected number. **Compute
   the verdict, never assert it** — it may stay FAIL or flip to PASS; either is reported as-is (honest-
   fallback, no cherry-picking — `reports/comparison.md` §4 ethos). Keep a clearly-labelled **before/after
   slice** in the report so the correction is transparent, not hidden.

   **Trajectory detection is structural, not a hard-coded S04/S11 list:** a scenario is "trajectory" iff
   **any** of its `ground_truth` teams has `trajectory != "flat"`; the week count is `max(week)` over the
   dataset's game log. This auto-covers any future drifting scenario and leaves all-flat scenarios on the
   existing static key with no behavioural change.

---

## Read first (in this order — a cold chat must absorb all of these)

1. **`CLAUDE.md`** — the prime directive (100% AI-authored, reviewed in chat; explain *why*/behavior, cite
   invariants not lines), **method §3** (observed-vs-derived is a hard wall; *always compute aggregates
   from the game log, never trust a stored summary*), **method §2** (determinism is sacred — I8/I9), and
   **the gate**. This task lives entirely on the *measurement* side of the wall.
2. **`docs/planning/operating-model.md`** — the task template, the trunk + PR "stop before merge" loop, the
   model-matching table (harness/metrics/scenarios → sonnet; model-core → opus — this task is **not**
   model-core), and the verification agents.
3. **`reports/comparison.md`** — the current decision artifact. Study **§2** (per-scenario Spearman: S04
   0.7143, **S11 −0.5000** vs mhr −0.1000 — the trajectory artifact; **S05 0.3571** vs mhr 0.9048 — the
   *structural* gap that stays), **§3** (gate verdict + scorable/excluded sets), **§4** (the honest
   diagnosis: **Cause 1 = the trajectory measurement artifact this task fixes**, **Cause 2 = the S05
   structural floor cost that stays**, and the "also set aside S04/S11" slice 0.8229 vs 0.8893), and **§6**
   (the recommended-follow-up bullet — this task).
4. **`harness/metrics.py`** — `score_model(ground_truth, result) -> MetricsResult` and the three metric
   helpers. **Why the artifact exists:** `true_ratings = {k: true_map[k].rating ...}` uses the *static*
   `TeamParams.rating`. This is the file you extend with a point-in-time truth helper + an optional truth
   override on `score_model` (see Approach). `tier_accuracy` and the centering logic are unchanged.
5. **`generator/simulate.py`** — `week_params(team, week) -> (attack, defense)` (already exported for
   exactly this purpose — see its docstring: *"so the harness can reconstruct per-week true ratings for I11
   scoring"*) and `TeamParams.rating = attack − defense`, `TeamParams.trajectory`. **For a `flat` team
   `week_params` returns the raw baseline**, so a point-in-time key equals the static key on static
   scenarios — that is what keeps them byte-identical. **Do not edit this file.**
6. **`scenarios/builders.py`** — `build_s04_stale_opponent` (T_EARLY_STRONG `falling`; 8 weeks) and
   `build_s11_momentum` (RISER `rising` / FALLER `falling`; `n_weeks = 8`, symmetric so their season
   *average* attack is equal but their end-of-season form is opposite — this is *why* the static key
   mis-scores them). Read both to see the drift; **no builder change is needed**.
7. **`harness/run.py`** — `run_rank_recovery()` (scores every `build_sNN` via `score_model`),
   `gate_verdict()` (mean Spearman over **scorable** scenarios — `numpy.std(true_ratings) > 1e-9`),
   `build_report()` / `_metric_table()` / `main()`, and the **§4 narrative strings** (the
   "point-in-time truth" language already drafted around line ~380 — update it from "recommended follow-up"
   to "done here"). `reports/comparison.md` **regenerates byte-identically** (asserted by
   `harness/test_run.py::test_report_is_deterministic`) — regenerate via `python -m harness.run`, never
   hand-edit. The scorable-set rule in `gate_verdict` keys off `numpy.std(true_ratings)`; if you swap the
   truth key for trajectory scenarios, make sure the *same* (point-in-time) vector drives both the score
   and the scorable test so they can't disagree.
8. **`harness/test_metrics.py`** and **`harness/test_run.py`** — the existing seams you extend (and must
   keep green). The determinism test in `test_run.py` is the guard that the regenerated report is stable.
9. **`scenarios/test_s04_stale_opponent.py`**, **`scenarios/test_s11_momentum.py`** — the §7 ordering
   tests (these assert team *orderings*, not metric scores, so they're unaffected; only touch them if you
   choose to add an explicit point-in-time scoring assertion).

---

## Approach (TDD — write the failing tests first, watch them fail, then implement)

### Step 1 — `harness/test_metrics.py` (extend; the scorer's new seam)

```python
# test_point_in_time_truth_equals_static_for_flat_teams:
#   For an all-flat ground_truth, point_in_time_truth(gt, n_weeks) == {t.id: t.rating} exactly.
#   (Static scenarios cannot move — the byte-identical guarantee.)

# test_point_in_time_truth_tracks_end_of_season_form_for_drifting_teams:
#   For a 'rising' and a 'falling' team symmetric in season average (mirror S11's construction),
#   point_in_time_truth ranks the riser ABOVE the faller at the last week, whereas the static
#   TeamParams.rating ranks them equal. (The artifact is in the key, and the new key fixes it.)

# test_score_model_default_path_is_unchanged:
#   score_model(gt, result) with no truth override returns exactly what it returns today on a
#   flat scenario (regression guard — the optional arg defaults to the static behaviour).

# test_score_model_uses_truth_override_when_supplied:
#   score_model(gt, result, truth_ratings=point_in_time) scores Spearman/RMSE against the override,
#   not TeamParams.rating; tier scoring is untouched.
```

### Step 2 — `harness/test_run.py` (extend; the wired-in gate)

```python
# test_trajectory_scenarios_scored_against_point_in_time_truth:
#   run_rank_recovery() scores S04/S11 against point-in-time truth (assert the S11 bespoke Spearman
#   is no longer the backwards -0.5 it is under the static key — it improves toward the correct
#   current-form ordering). Static scenarios (e.g. S07) score identically to before.

# test_report_is_deterministic:
#   (existing) still green — regenerated report is byte-identical across two builds.

# test_gate_verdict_is_computed_not_asserted:
#   gate_verdict over the re-scored recovery yields a bool consistent with the actual means
#   (PASS or FAIL — whichever the numbers give; the test asserts the verdict matches the recomputed
#   mean comparison, not a hard-coded PASS).
```

### Step 3 — implement to green

1. **`harness/metrics.py`** — add `point_in_time_truth(ground_truth, n_weeks) -> dict[str, float]` (maps
   each team id to `week_params(t, n_weeks)` → attack − defense; for `flat` teams this is `t.rating`), and
   give `score_model` an optional `truth_ratings: dict[str, float] | None = None` that, when provided,
   replaces the static `true_ratings` for the Spearman/RMSE comparison (tier scoring unchanged). Default
   `None` ⇒ today's behaviour exactly. Comment the *why* (point-in-time = generator ground truth at
   end-of-season; observed-vs-derived wall intact).
2. **`harness/run.py`** — in `run_rank_recovery()`, detect trajectory scenarios (`any(t.trajectory !=
   "flat" for t in dataset.ground_truth)`), compute `point_in_time_truth(dataset.ground_truth,
   max(g.week for g in dataset.games))`, and pass it as `score_model(..., truth_ratings=...)`; all-flat
   scenarios pass nothing. Update the **§4 narrative** in `build_report` so it reads as *resolved* (S04/S11
   now scored against point-in-time truth; keep the before/after slice; restate that the **S05 gap is the
   deliberate structural floor cost that remains**). Keep all numbers generated, not typed.
3. `python -m harness.run` → regenerate `reports/comparison.md`. Confirm: the matrix still shows bespoke ✓
   across I1–I13 (untouched — the model didn't change); S04/S11 re-scored; the before/after slice present;
   the S05 caveat stays; the gate verdict reflects the recomputed means.
4. Run `pytest -q` (whole suite green) and `ruff check .`.

---

## Acceptance / Definition of done

- [ ] `harness/metrics.py` — `point_in_time_truth` added; `score_model` takes an optional truth override
      that defaults to **today's static behaviour** (no static-scenario number moves).
- [ ] New tests in `harness/test_metrics.py` and `harness/test_run.py` green; **all existing metrics/run
      tests still green and unweakened** (especially `test_report_is_deterministic`).
- [ ] `run_rank_recovery` scores **S04 and S11 against point-in-time truth**; the S11 bespoke Spearman is
      no longer the backwards −0.50 (it reflects the correct current-form ordering); static scenarios
      (e.g. S07) score identically to before.
- [ ] `reports/comparison.md` regenerated via `python -m harness.run`; byte-identical determinism test
      green; the S04/S11 artifact visibly removed (with a clearly-labelled before/after slice); the **S05
      structural gap is noted as expected-to-remain** (a deliberate cost of the fairness floor, not a
      measurement choice); the gate verdict is whatever the recomputed means give (PASS or FAIL — computed,
      not asserted; no cherry-picking).
- [ ] `models/bespoke.py` and `generator/*` **untouched**; `scenarios/builders.py` untouched (only the §7
      *test* files touched, and only if you add a point-in-time scoring assertion).
- [ ] `pytest -q` whole suite green; `ruff check .` clean.
- [ ] **`spec-keeper`** run on the diff — confirm the observed-vs-derived wall holds (point-in-time truth is
      generator ground truth via `week_params`, never a recovered rating fed back), determinism preserved
      (I8 — `week_params` is pure), and no scenario/metric was weakened to flatter the gate. Include its
      verdict in the PR. (`invariant-auditor` is **not** required — no model change; note that in the PR.)
- [ ] `docs/work/BOARD.md` row 14 flipped (loop handles `in-progress`/`in-review`; merge → `done`); the
      ▶ Ready-now follow-up note marked resolved.
- [ ] PR body (plain English, reviewer won't open the file): lead with *why* (the season-average answer key
      scored a current-form model backwards on drifting teams) and *what behaviour changed* (trajectory
      scenarios now scored against end-of-season point-in-time truth, a pure generator value — wall intact;
      static scenarios byte-identical), the **before/after S04/S11 numbers and gate verdict**, and the
      explicit note that the **S05 structural gap remains by design**.

---

## Out of scope

- **Any change to `models/bespoke.py`** — the model is settled (TASK-13). This is a measurement change only.
- **Editing `generator/*`** — `week_params` already exports exactly the per-week truth needed; consume it.
- **Editing `scenarios/builders.py` or planting new ground truth** — trajectory is already on `TeamParams`
  and the week count is read from the log; no builder change is needed.
- **"Fixing" the S05 giant-killer gap** — it is a deliberate *structural* cost of the fairness floor (I1),
  not a measurement artifact, and is expected to remain. Do not tune or slice it away.
- **Adding/removing invariants or scenarios**, or weakening any test to move the gate (honest-fallback
  forbids cherry-picking).
- **Stage B** (walk-forward / log-loss / real-data calibration) — out of scope for the whole spike.
