# TASK-13: Stage-A tuning of the strawman parameters

**State:** ready · **Model:** opus — this is **model-core** work: it sets the shipped defaults of
`models/bespoke.py` (α, ρ, ρ_tier, λ, and the floor/bonus/tier tables stay structural). It is the
final link in the sequential core-model chain (05 → 06 → **13**) and the task that decides whether the
spike's **gate** is met. Ambiguity is high (a multi-objective tuning call with a fairness-floor
constraint), cost-of-error is high (it overwrites the model's defaults) → opus, never stepped down.
**Owns (files):** `models/bespoke.py` (the `BespokeParams` defaults + `rate_weekly`'s `rho`/`rho_tier`
defaults — values only, not the floor/solve structure), `models/test_bespoke_tuning.py` (new — guards
the tuned outcome), `harness/tune.py` (new — the deterministic sweep that *produces and documents* the
chosen params), `harness/test_tune.py` (new — the sweep's seams), `reports/comparison.md` (regenerated
artifact). Doc updates (not contended): `docs/analysis/decision-memo.md` §9/§11, `docs/work/BOARD.md`.
**Parallel-safe:** **no** — owns `models/bespoke.py` (the core). Never run beside any other core task,
and nothing that changes a model, scenario, metric, or the harness MATRIX may be in flight (this task
re-scores every model against every scenario and regenerates the decision artifact).
**Depends on:** TASK-11 (done — the §7 scenario suite + the α-at-reachable-gap finding) and TASK-12
(done — `harness/run.py`, `score_model`, and `reports/comparison.md`, the gate machinery this task
re-runs). Both `done`.
**Branch from:** latest `main` (`0255432`) — the `/task 13` loop handles branch + PR.

> **Heads-up on the starting state:** `main` is green **except one deliberately-left red** —
> `scenarios/test_s07_close_vs_tier.py::test_s07_i6_credit_loss_elite_beats_win_weak`. It fails *by
> design* at the shipped α=0.6 (it `pytest.fail`s loudly with the α re-derivation target rather than
> xfail-ing). **Turning that red green by re-deriving α is part of this task's DoD** — do not delete,
> skip, or weaken the test. Confirm the baseline before you start: `pytest --tb=no -q` should show
> exactly this one failure and nothing else.

---

## Goal

Tune the bespoke model's **strawman parameters** (memo §9) from their hand-picked starting values to a
**defensible, deterministic, invariant-safe** parameterization that (1) makes **end-to-end I6** hold at
the solver's *reachable* converged spread — re-deriving α against the real gap (≈4.38), not the
hand-picked +4/−2 example — and (2) closes the **rank-recovery** gap so bespoke **beats the MHR replica**
on mean Spearman ρ over the scorable §7 scenarios. The output that ships is the new `BespokeParams`
defaults plus `rate_weekly`'s `rho`/`rho_tier` defaults; the *evidence* is a committed, reproducible
sweep (`harness/tune.py`) and a regenerated `reports/comparison.md` whose gate verdict flips to **PASS**.

This is **Phase 6 → decision** of `docs/planning/PLAN.md` and the moment the spike's gate is settled:
*bespoke passes every I1–I13 **and** beats the MHR replica on Stage-A rank recovery.* TASK-12 proved the
fairness half outright (bespoke holds all I1–I13) but, at untuned defaults, reported the accuracy half as
an honest **FAIL** (mean Spearman bespoke 0.6811 vs mhr 0.7769). This task is where the *improvements*
are made to earn the accuracy win — not by matching what MHR happens to do, but by tuning our own knobs
within the fairness-safe region.

**Two findings carried in from TASK-11/12 that you must address head-on:**

1. **Re-derive α against the reachable gap (memo §11 Q1, BOARD α-note).** At α=0.6 the schedule term
   clears `W−L=3` only on the harness's hand-built +4/−2 construction (gap 6). On the *real* solver
   spread the converged gap is `R_TOP − R_BOTTOM ≈ 4.38`, so `0.6 × 4.38 = 2.63 < 3.00` and a narrow
   loss to the elite is *out-credited by* a narrow win over the worst — I6 inverts end-to-end (the S07
   red). I6 needs `α × 4.38 > 3 ⇒ α ≳ 0.69`; α=0.8 clears it with margin. **α must land high enough to
   satisfy S07 end-to-end while staying `< 1` for the I9 contraction** (`α(1−λ) < 1`; at λ=0.05, α<1.05,
   so α<1 with margin). Note α also *changes* the converged gap, so confirm I6 by **re-running the S07
   test at the candidate α**, not by arithmetic on the old gap.

2. **The trajectory-vs-static-truth measurement gap (S04, S11) is a *measurement* artifact, not a model
   defect — handle it honestly, do not tune it away.** `score_model` grades each team against its
   **static** planted rating (`attack − defense`), i.e. the season *average*. Bespoke's recency
   weighting is built to track *current* form (that is what I11 demands), so on the trajectory scenarios
   it is scored **backwards** (S11: bespoke −0.50 vs mhr −0.10 — ranking the rising team above the
   falling one is the correct *current-form* call but disagrees with the season-average answer key).
   Cranking ρ toward 0 would raise those scores by *killing the I11 feature* — that is forbidden (I11 is
   a hard constraint; the fairness/feature floor is not a tuning surface). The right handling is a
   **metric/scenario note**, and — if the residual gap to MHR is *only* the trajectory artifact — a
   recommended **follow-up task** to score trajectory scenarios against point-in-time truth. See
   "Decision criterion & honest-fallback" below.

---

## Read first (in this order — a cold chat must absorb all of these)

1. **`CLAUDE.md`** — the prime directive (100% AI-authored, reviewed in chat; explain *why*/behavior,
   cite invariants not lines), the **method** (§5: "every tuning pick is a falsifiable assumption with a
   named confirming scenario; the test, not the pick, has the final word"; §4: the fairness floor is
   **structural, not tuned** — `base` is untouchable, the two opponent-strength channels stay
   orthogonal), **determinism is sacred (I8/I9)**, and **the gate** ("must pass all invariants I1–I13 on
   the §7 scenarios **and** beat the MHR replica on rank-recovery").
2. **`docs/planning/operating-model.md`** — task template, the **opus model-core rule** ("anything
   touching `models/bespoke.py`'s floor/solve is opus"), the trunk + PR "stop before merge" loop, and
   the **verification agents** (`invariant-auditor`, `spec-keeper`) that are mandatory after a
   model-core change.
3. **`docs/analysis/decision-memo.md`:**
   - **§9 — strawman defaults** (the table you are tuning): `W/T/L = 3/1/0`; `bonus[3/4/5+] =
     0.6/0.9/1.0`; `pen[3/4/5+] = 0.5/0.8/1.0`; **`α = 0.6`, "sweep 0.3–0.8 in Stage A"**; `ρ` ≈ ½-life
     3–4 weeks; `λ = 0.05`; `freezeWindowWeeks = 4`; `ρ_tier = ρ`. **These are starting points Stage A
     tunes — that is this task.**
   - **§11 — resolved design decisions** (each a *falsifiable assumption with a confirming test*): **Q1
     α** ("derived, not guessed … TASK-11 must re-derive α against the *reachable* gap … *falsified if*
     no α clears I6 end-to-end without breaking convergence or recovery"), **Q2 T** (sensitivity
     `T∈{0.5,1,1.5}`), **Q3 tier mod** (the ablation that proves the two opponent channels aren't
     redundant — *do not collapse them*), **Q4 weak-team win** (bounded debit in `scheduleTerm` only).
     **The decision criterion (ranked) is stated at the top of §11 — copy it; it governs your tuning
     objective.**
   - **§10 — invariant → mechanism map** (what each I1–I13 is guaranteed by; your tuning must not break
     any mechanism — e.g. α stays `<1` for the §3 contraction; `base` floor untouched).
   - **§3** — determinism/convergence/uniqueness (the contraction argument; α enters the coupling, so a
     higher α must still satisfy `α(1−λ) < 1`).
4. **`docs/planning/PLAN.md`** Phase 6 ("Run, review, decide") and the **"Definition of done for the
   spike"** list — items 2 (passes invariants on scenarios) and 3 (**beats MHR on Stage-A rank
   recovery**) are exactly what this task must turn green.
5. **`reports/comparison.md`** — the current decision artifact (untuned-defaults snapshot). Study **§2**
   (the per-scenario Spearman table — see where bespoke loses: **S05 giant-killer 0.3571 vs mhr 0.9048**
   is the biggest *static* loss and the richest tuning target; S03 0.7133 vs 0.8531; S11 −0.50 is the
   trajectory artifact), **§3** (the gate verdict + scorable/excluded sets), **§4** (the honest
   "why the accuracy half reads as it does", incl. the *also-set-aside-trajectory* slice: 0.8166 vs
   0.8893 — bespoke still trails, so tuning must improve the *static* scenarios too), and **§6**
   (the α/I6 caveat that is this task's job to resolve).
6. **`models/bespoke.py`** — the full file. What you touch and what you must NOT:
   - **`BespokeParams`** — change the **default values** of `alpha` (and, if the sweep selects them,
     `win_bonus`/`loss_penalty` *scales* and the `tier_m`/`tier_p` *strengths*). **Do NOT** change the
     *structure*: `win > tie > loss`, `win_bonus ≥ 0` and non-decreasing with `close = 0`,
     `loss_penalty ≥ 0` with `close = 0`, both tier modulators `≥ 0` (these are what make I1–I5/I7 hold
     *structurally* — see the field comments). Tier 3 must stay the neutral baseline (`m = p = 1.0`) so
     the fixed-`opp_tier=3` credit tests are unperturbed.
   - **`rate_weekly`** signature defaults `rho=0.2`, `rho_tier=0.2` — tune these *values* (memo §9 range
     ~0.1–0.4). Keep `rho = rho_tier` unless the sweep gives a clear, documented reason to split them
     (memo §9 says `ρ_tier = ρ`).
   - **`rate`** (the flat baseline) passes `rho=0.0` — **leave that untouched**; its byte-identical ρ=0
     path is what keeps the `rate()` I8/I9 + credit + cross-opponent tests green.
   - The **floor/solve machinery** (`base_and_margin`, `scaled_margin`, `_solve`, `_attribute`, the
     contraction) is **not** yours to restructure — you are choosing *constants*, not rewriting the
     model. If tuning seems to need a structural change, stop and flag it (likely a different task).
7. **`harness/run.py`** — `run_invariant_matrix()`, `run_rank_recovery()`, `gate_verdict()`,
   `build_report()`, `main()`. This is the **scoreboard you optimize against and regenerate**:
   `run_rank_recovery()` scores `bespoke_weekly`/`mhr`/`ridge` over all 13 `build_sNN` datasets via
   `score_model`; `gate_verdict()` computes `bespoke_beats_mhr` as mean Spearman over **scorable**
   scenarios (`numpy.std(true_ratings) > 1e-9`). Your sweep should reuse these exact primitives so the
   number you tune *is* the number the gate reads. **`reports/comparison.md` regenerates
   byte-identically** (asserted by `harness/test_run.py::test_report_is_deterministic`) — so after you
   change the defaults, re-running `python -m harness.run` is the canonical way to refresh the artifact,
   and its determinism test still holds (same code → same bytes).
8. **`harness/metrics.py`** — `score_model(ground_truth, result) -> MetricsResult(spearman_rho,
   centered_rmse, tier_accuracy, …)`. **Read why the trajectory gap exists:** `true_ratings` uses
   `TeamParams.rating = attack − defense` (the *static* season value) — there is no point-in-time truth,
   so a recency-tracking model is scored against a season-average key on S04/S11. You may **not** edit
   this file (TASK-10 owns it); you *document* the artifact and, if it's the deciding factor, recommend
   a follow-up.
9. **`harness/adapters.py`** — the `bespoke_weekly`, `mhr`, `ridge` adapters (`(list[GameRow]) ->
   RateResult`). The rank-recovery pass uses `bespoke_weekly` (full tier+trend candidate). Your sweep
   evaluates `bespoke_weekly` under candidate `BespokeParams`/`rho` — make sure the adapter (or a thin
   parameterized variant in `tune.py`) threads the candidate params through; do not hard-fork the model.
10. **`scenarios/builders.py`** — the 13 `build_sNN(...) -> (Dataset, dict)`; `Dataset.games` feed the
    model, `Dataset.ground_truth: list[TeamParams]` feeds `score_model`. **`build_s07_close_vs_tier`** is
    the I6 construction (T_TOP/T_BOTTOM/T_SUBJECT) and **`build_s05_giant_killer`** is the biggest static
    loss — read both to understand what a better α / tier-table buys you.
11. **`scenarios/test_s07_close_vs_tier.py`** — the **end-to-end I6** test (currently red) and the α=0.8
    sweep test. This is your I6 acceptance gate: `test_s07_i6_credit_loss_elite_beats_win_weak` must go
    **green at the shipped default α** (it reads `BespokeParams().alpha`), and the α=0.8 sweep test must
    stay green. **Do not weaken either** — re-derive α so they pass for real.
12. **`harness/test_harness.py`** (the `MATRIX`) and **`harness/invariants.py`** (the `check_I*`) — the
    model-agnostic I1–I13 checks that `run_invariant_matrix()` re-runs. After re-tuning, every bespoke
    cell must still read **✓** (no `✗ FAIL`, no `XPASS`). `invariant-auditor` re-runs these against your
    chosen params.

---

## Decision criterion & honest-fallback (settled by CLAUDE.md §5 + memo §11 — do not re-debate)

**Ranked objective (memo §11 top):** (1) **invariant safety** — never risk a fairness floor; structural
beats tuned. (2) **rank-recovery vs planted truth** — the scoreboard. (3) explainability (fewer knobs,
legible values). (4) robustness/determinism. Tie-break: fidelity to brief intent.

**Hard constraints — true for *any* shipped parameterization (verified, not assumed):**
- All **I1–I13 pass** (the `MATRIX` cells stay ✓; `invariant-auditor` confirms). The floor structure
  (`W>T>L`, bonuses/penalties ≥0 with `close=0`, tier mods ≥0, tier 3 neutral) is **kept by
  construction** — you tune *magnitudes within the safe region*, never the structure.
- **End-to-end I6 holds:** `scenarios/test_s07_close_vs_tier.py` goes fully green at the shipped α.
- **I9 contraction preserved:** `α(1−λ) < 1` (re-confirm at the chosen α/λ); the solver still converges
  deterministically (I8) — `invariant-auditor` checks convergence/determinism at the new defaults.
- **I11 is not sacrificed for score.** ρ may be tuned *within* the memo range, but the rising/falling
  trend-sign separation and current-form ordering (`models/test_bespoke_trend.py`) must stay green. You
  may **not** push ρ→0 to win back the trajectory scenarios.

**Objective:** maximize mean Spearman ρ over the **scorable** scenarios (the same set & rule
`gate_verdict` uses) **subject to** the hard constraints. **Gate target:** bespoke mean Spearman >
mhr mean Spearman ⇒ `gate_verdict(...).bespoke_beats_mhr is True` ⇒ `reports/comparison.md` overall
verdict flips to **PASS**.

**Honest-fallback (no cherry-picking — this is the project's ethos, see comparison.md §4):** If, after a
genuine invariant-safe sweep, bespoke **cannot** beat MHR on the full scorable set, **do not** exclude
scenarios or weaken a test to manufacture a win. Instead:
- Ship the **improved** params anyway (re-derived α fixes I6; better tuning lifts the static scenarios) —
  this is strictly better than the untuned defaults even if the gate stays FAIL.
- **Diagnose the residual gap precisely** in the report: if it is *only* the trajectory measurement
  artifact (S04/S11 scored against static truth), say so with the slice evidence (the "also set aside
  S04/S11" mean), and add a **metric/scenario note** + a recommended **follow-up task** (e.g. "TASK-14:
  score trajectory scenarios against point-in-time truth in `harness/metrics.py`/`scenarios`"), which
  TASK-13 cannot do itself (it does not own those files).
- Report the result **as-is** with the honest call, exactly as TASK-12 did. The gate verdict is computed,
  never asserted by prose.

---

## Architecture decisions (settled — do not re-debate)

**The sweep is a committed, deterministic artifact (`harness/tune.py`), not a throwaway.** The chosen
params must be *reproducible and auditable* — "why these values" has to survive into the demo. So
`tune.py` defines an explicit, **finite, fixed-order grid** over the tuning axes, evaluates each point by
re-using `harness.run.run_rank_recovery`-style scoring (`score_model` over the scorable scenarios) **plus**
a hard-constraint check (S07 I6 + the contraction bound), and returns the argmax under a **stated,
deterministic tie-break** (e.g. highest mean Spearman; ties broken by *smaller* α, then values closest to
the memo §9 strawman — the principle: prefer the least exotic knob that wins). **No RNG, no wall-clock,
stable iteration order** (I8 ethos): re-running the sweep yields byte-identical results, asserted by a
test. Each axis is documented in `tune.py` as a *falsifiable assumption with its confirming scenario*
(memo §11 ethos): α↔S07/I6, ρ↔S11/I11 + trajectory cost, tier-table strength↔S05/giant-killer.

**Tuning axes (the grid — keep it small, legible, and inside the safe region).** Primary:
- **`alpha`** ∈ a grid with floor ≥ 0.7 (must clear I6 at the reachable gap) and ceiling < 1 (contraction
  margin), e.g. `{0.70, 0.75, 0.80, 0.85, 0.90}`. This is the single most important axis (it fixes I6
  *and* moves recovery).
- **`rho` (= `rho_tier`)** ∈ the memo range, e.g. `{0.1, 0.2, 0.3, 0.4}`. Document the trajectory trade:
  lower ρ scores S04/S11 better but weakens current-form tracking; the choice must keep
  `models/test_bespoke_trend.py` green.
- Optionally **a single tier-table strength multiplier** (scales `tier_m`/`tier_p`'s *distance from the
  neutral 1.0*, keeping tier 3 = 1.0 and all entries ≥ 0) if S05 needs it — one knob, not eight, for
  legibility (criterion 3). Keep `scheduleTerm` and the tier table **orthogonal** (memo §11 Q3): do not
  also widen α to compensate for a weak tier table — that double-counts opponent strength.

Hold `λ = 0.05` (it sets uniqueness, not accuracy; memo §9) and the `W/T/L = 3/1/0` floor fixed unless
you can show, with a confirming test, that moving them helps *without* touching invariant safety — and
prefer not to (criterion 3: fewer knobs). Do **not** sweep the floor itself.

**The shipped defaults are the sweep's argmax — and a test pins that.** After the sweep names the
winner, write those exact values into `BespokeParams` / `rate_weekly` defaults. A test asserts the
*shipped* defaults satisfy the hard constraints and beat MHR (the regression guard), and — for
reproducibility — that `tune.py`'s argmax equals the shipped values. Keep the full-grid sweep **out** of
the always-on suite if it is slow; expose it as `harness.tune.main()` / a `-m harness.tune` entry and let
the *guard* test assert only the chosen point (fast), with the determinism of the sweep covered by a
small fixed sub-grid in `test_tune.py`.

**Regenerate the decision artifact, don't hand-edit it.** After changing defaults, run
`python -m harness.run` to rewrite `reports/comparison.md`; its byte-identical-determinism test
(`harness/test_run.py::test_report_is_deterministic`) must stay green. Update the report's narrative
sections only **through the generator** (`build_report` in `run.py` is owned by TASK-12 and is *done* —
if the prose needs to change, that is a `run.py` edit; prefer to let the *numbers* tell the story and add
any new caveat via the existing "Caveats / open items" mechanism). If `run.py` prose must change to
reflect the resolved α and the trajectory note, that edit is in-scope here (it is the report's source).

---

## TDD approach — write the tests first, watch them fail, then implement

### Step 1 — `harness/test_tune.py` (new; the sweep's seams)

Pure `def test_*` functions; build inputs by calling `tune.py`'s own functions.

```python
# test_grid_is_finite_and_in_safe_region:
#   Every alpha in the grid is >= 0.7 and < 1.0 (I6 floor + contraction ceiling);
#   every rho in [0.1, 0.4]; the tier-strength multiplier (if present) keeps all tier_m/tier_p >= 0
#   and tier 3 == 1.0. (The grid can't propose an invariant-unsafe point.)

# test_score_point_uses_scorable_set:
#   score_point(params, rho) returns a mean Spearman computed over exactly the scorable scenarios
#   (numpy.std(true_ratings) > 1e-9) — same set gate_verdict uses. (Reuse harness.run primitives.)

# test_hard_constraint_filter_rejects_low_alpha:
#   A candidate with alpha below the I6-reachable threshold (e.g. 0.6) fails the S07/I6 hard check,
#   so the sweep never selects it. (The constraint check, not the score, gates selection.)

# test_sweep_is_deterministic:
#   run_sweep(small_fixed_subgrid) twice returns identical (winner, full ranking) — no RNG, stable order.

# test_winner_beats_mhr_or_reports_honest_gap:
#   The sweep returns a result object exposing winner mean Spearman for bespoke vs mhr; assert it is
#   either bespoke > mhr (gate met) OR carries a documented residual-gap diagnosis (the honest-fallback
#   path is representable, not a crash).
```

### Step 2 — `models/test_bespoke_tuning.py` (new; guards the shipped outcome)

```python
# test_shipped_alpha_satisfies_end_to_end_I6:
#   With BespokeParams() defaults, re-run the S07 construction (import build_s07_close_vs_tier);
#   credit(loss→T_TOP) > credit(win→T_BOTTOM). (Mirrors the scenario test against the SHIPPED default.)

# test_shipped_defaults_preserve_contraction:
#   BespokeParams().alpha * (1 - lam_default) < 1.0  (I9 stays a contraction at the new alpha).

# test_shipped_defaults_keep_floor_structure:
#   win > tie > loss; win_bonus monotone non-decreasing & close == 0; loss_penalty close == 0 & >= 0;
#   all tier_m/tier_p >= 0; tier_m[2] == tier_p[2] == 1.0 (tier 3 neutral). (Structural I1-I5/I7 intact.)

# test_shipped_defaults_beat_mhr_or_document_gap:
#   Using harness.run.gate_verdict(run_invariant_matrix(), run_rank_recovery()):
#   v.bespoke_all_invariants_pass is True AND (v.bespoke_beats_mhr is True
#     OR the residual gap is exactly the documented trajectory set — see honest-fallback).
#   (If the gate is met, this is the hard 'beats MHR' assertion; keep it strict.)

# test_shipped_defaults_keep_I11_trend:
#   Re-run the rising/falling construction (mirror models/test_bespoke_trend.py): trend signs still
#   separate and current-form ordering holds at the shipped rho. ( rho wasn't pushed to 0 for score.)
```

### Step 3 — implement to green

1. `harness/tune.py` — the fixed grid, `score_point`, the hard-constraint filter (S07/I6 +
   contraction), `run_sweep` (deterministic, stable order, stated tie-break) returning the winner +
   ranking, and `main()` that prints/persists the chosen params + the per-point table (the auditable
   "why"). Reuse `harness.run`/`harness.adapters`/`harness.metrics` — do not re-implement scoring.
2. Write the **winning values** into `models/bespoke.py` (`BespokeParams` defaults + `rate_weekly`
   `rho`/`rho_tier`). Update the field comments to state the *derived* α (cite the reachable gap ≈4.38
   and the S07 confirming test) and the ρ choice (cite the I11/trajectory trade) — comments explain
   *why*, per CLAUDE.md.
3. `python -m harness.run` → regenerate `reports/comparison.md`. Confirm the gate verdict and the
   trajectory caveat read correctly. If the narrative needs the resolved-α / trajectory-note wording,
   edit `build_report` in `run.py` (its determinism test must stay green).
4. Update **memo §9** (strawman → tuned defaults, with a "tuned in TASK-13" note) and **§11 Q1** (mark α
   resolved: derived value, reachable-gap evidence, confirming test). Update **`docs/work/BOARD.md`**
   (flip 13's row to `in-review`/`done` per the loop; refresh the α-finding note to "resolved").
5. Run `pytest -q` (whole suite green — **including the formerly-red S07**) and `ruff check .`.

---

## Acceptance / Definition of done

- [ ] `scenarios/test_s07_close_vs_tier.py` — **both** tests green at the shipped default α (the
      formerly-red end-to-end I6 test now passes for real; α=0.8 sweep test still green). Test
      unweakened.
- [ ] `models/test_bespoke_tuning.py` and `harness/test_tune.py` — all new tests green.
- [ ] `BespokeParams` / `rate_weekly` defaults updated to the sweep's argmax; floor/solve **structure
      unchanged** (only constants moved); `rate()`'s ρ=0 path untouched.
- [ ] Existing core tests still green & unweakened: `models/test_bespoke_rate.py`,
      `models/test_bespoke_credit.py`, `models/test_bespoke_cross_opponent.py`,
      `models/test_bespoke_trend.py` (I11 preserved — ρ not sacrificed). Inequality-based tests re-run,
      not loosened.
- [ ] `reports/comparison.md` regenerated via `python -m harness.run`; **byte-identical determinism test
      green**; the matrix still shows bespoke ✓ across I1–I13; the gate verdict reflects the tuned result
      (PASS if bespoke beats MHR; otherwise the honest-fallback diagnosis with the trajectory note +
      recommended follow-up — no cherry-picking).
- [ ] `pytest -q` — **whole suite green** (zero failures, including S07). `ruff check .` clean.
- [ ] **`invariant-auditor`** run against `models/bespoke.py` at the new defaults — adversarially
      confirm I1–I13 hold (focus: I6 end-to-end at the reachable gap, I8/I9 determinism+contraction at
      the higher α, I1–I5/I7 floor structure intact, I11 trend preserved). Include its verdict in the PR.
- [ ] **`spec-keeper`** run on the diff — confirm no floor breach (`base` untouched), the two
      opponent-strength channels stay orthogonal (α not widened to cover a weak tier table — no
      double-counting, memo §11 Q3), determinism preserved, and no derived value fed back as input.
      Include its verdict in the PR.
- [ ] Memo §9/§11 Q1 updated (defaults tuned; α resolved with reachable-gap evidence + confirming test).
- [ ] `docs/work/BOARD.md` row 13 flipped (loop handles `in-progress`/`in-review`; merge → `done`); the
      α-finding note marked resolved.
- [ ] PR body (plain English, reviewer won't open the file): lead with *why* and *what behavior changed*
      — the new α (and the reachable-gap derivation that makes I6 hold end-to-end), the ρ/tier choices
      and the scenarios that confirm them, the **before/after mean Spearman** (bespoke vs mhr) and the
      gate verdict, the invariant-safety argument (cite I6/§11 Q1, I9 contraction `α(1−λ)<1`, the
      structural floor untouched, I11 preserved), the `invariant-auditor`/`spec-keeper` verdicts, and —
      if the gate stays FAIL — the honest trajectory-artifact diagnosis + recommended follow-up.

---

## Out of scope

- **Restructuring the model** (floor/solve/attribution machinery, the contraction, the tier-detection or
  frozen-window logic). This task chooses *constants*; if tuning seems to need a structural change, stop
  and file it — it is a different (opus core) task.
- **Editing `harness/metrics.py` or the scenario builders/ground truth** (TASK-10 / TASK-11 own them).
  The trajectory measurement gap is *documented and recommended as a follow-up* here, not fixed —
  scoring trajectory scenarios against point-in-time truth is a new task.
- **Adding or removing invariants / scenarios**, or weakening any test to pass the gate (the honest-
  fallback forbids cherry-picking).
- **Benchmarks, generator, JSON serialization** changes.
- **Stage B** (walk-forward / log-loss / calibration on real data) — out of scope for the whole spike.
- **Margin-Elo / Poisson-as-rater** benchmarks (PLAN Phase 4 — deferred unless the decision is close).
- **Charts/plots/HTML or the hosted demo UI** — Markdown tables only; the demo is a later phase.
