# TASK-10: Truth-scoring metrics (Spearman/RMSE/tier acc)

**State:** ready · **Model:** sonnet
**Owns (files):** `harness/metrics.py` (new), `harness/test_metrics.py` (new)
**Parallel-safe:** yes — both files are new; disjoint from all other tasks
**Depends on:** none (generator format locked in `generator/simulate.py`; harness adapter interface locked in `harness/adapters.py`)
**Branch from:** latest `main` (`a57edaf`) — the `/task 10` loop handles branch + PR

---

## Goal

Build `harness/metrics.py`: a model-agnostic module that scores a `RateResult` against the
generator's planted ground truth. Three metrics are needed:

1. **Spearman ρ** — rank correlation between recovered and true ratings; the primary "did we
   get the order right?" score for Stage-A rank recovery.
2. **Centered RMSE** — RMS error of model ratings vs true ratings, both centered to zero mean
   first (rating magnitude is arbitrary; only relative position matters).
3. **Tier accuracy** — fraction of teams placed in the correct tier vs true tiers from
   `TeamParams.tier`, under the best-matching label permutation (see Architecture decisions).

Expose a `score_model(ground_truth, result) -> MetricsResult` bundle so TASK-12 (comparison
runner in `harness/run.py` + `reports/`) can call one function per model per scenario.

---

## Read first (in this order — a cold chat must absorb all of these)

1. **`CLAUDE.md`** — prime directive (100% AI-authored, reviewed in chat), TDD rule, observed-
   vs-derived wall (metrics *consume* `RateResult` outputs only — they never feed scores back
   into any solve), determinism is sacred.
2. **`docs/planning/operating-model.md`** — task template, sonnet model rule, trunk + PR loop,
   the "stop before merge" gate.
3. **`docs/planning/PLAN.md`** Phase 3 paragraph: *"truth-scoring (Spearman/Kendall rank
   recovery, centered RMSE/MAE, tier-boundary accuracy)"* — this is the spec anchor.
4. **`generator/simulate.py`** — `TeamParams` dataclass (`.id: str`, `.rating = attack − defense`,
   `.tier: int | None`), `Dataset` (`.games: list[GameRow]`, `.ground_truth: list[TeamParams]`).
   These supply the truth side of every metric call.
5. **`models/bespoke.py`** — `RateResult` dataclass: `.ratings: dict[str, float]`,
   `.tiers: dict[str, int]`, `.trend: dict[str, float]`, `.per_game_attribution`, `.center_offset`.
   `tiers` may be `{}` (flat `rate()` path). This is the result side of every metric call.
6. **`harness/adapters.py`** — `ModelFn` type and the four registered adapters. Confirm that all
   return `RateResult`; metrics must work with any adapter's output without model-specific imports.
7. **`harness/invariants.py`** — skim for style: model-agnostic, clear assertion messages, no
   model-specific imports in the check layer. Follow the same conventions in `metrics.py`.

---

## Architecture decisions (settled — do not re-debate)

**Centering for RMSE.** Both the true ratings vector and the model ratings vector are centered
to zero mean before computing RMSE: `v_c = v − mean(v)`. Bespoke already centers
(`mean(r) = 0`, memo §2), but we do not rely on that: always center both sides. This makes
the metric independent of the models' absolute scale conventions.

**Spearman only (not Kendall) for Stage A.** Spearman ρ is sufficient for the Stage-A rank-
recovery decision and simpler to validate. Kendall τ is a one-function addition if Stage B
needs pairwise-stability scoring; out of scope here.

**No scipy — numpy only.** Compute Spearman via `numpy.argsort` on both vectors, then
`numpy.corrcoef` on the rank arrays. This keeps the dependency footprint minimal and the
implementation readable.

**Tier accuracy — best-matching label permutation.** The generator assigns `TeamParams.tier`
as integers (1 = elite, 2 = next band, …); the model's `tiers` dict uses the same convention
(`detect_tiers` in `models/tiers.py` also labels 1 = top tier). For Stage-A synthetic datasets
the labels should agree, but do not assume this: find the bijection between label sets that
maximizes the fraction correct and report that maximum. For ≤5 tiers (the expected range) the
permutation space is tiny (≤120); iterate all permutations with `itertools.permutations`.
Teams whose `TeamParams.tier is None` are excluded from `n_tiers_scored`; if `result.tiers` is
empty or `n_tiers_scored == 0`, return `tier_accuracy = 0.0`.

**`MetricsResult` dataclass (the TASK-12 interface).**

```python
@dataclass(frozen=True)
class MetricsResult:
    spearman_rho: float      # Spearman rank correlation vs true ratings; range [-1, 1]
    centered_rmse: float     # RMSE after centering both vectors; ≥ 0; lower is better
    tier_accuracy: float     # fraction correct under best-matching permutation; [0, 1]
    n_teams: int             # teams present in both ground_truth and result.ratings
    n_tiers_scored: int      # teams with a non-None true tier included in tier_accuracy
```

**`score_model` signature (the TASK-12 call-site).**

```python
def score_model(
    ground_truth: list[TeamParams],
    result: RateResult,
) -> MetricsResult:
    ...
```

Only teams present in *both* `ground_truth` (by `.id`) *and* `result.ratings` (by key) are
included. `n_teams` records the intersection size. A team in `ground_truth` but absent from
`result.ratings` (e.g. a model that drops a team) is silently excluded; TASK-12 can log if
`n_teams < len(ground_truth)`.

---

## TDD approach — write the tests first, watch them fail

### Step 1 — `harness/test_metrics.py` (all new)

Write each test as a plain `def test_*` pytest function. No fixtures required; all inputs are
constructed inline.

```python
# test_spearman_perfect:
#   true_ratings  = {"A": 3.0, "B": 2.0, "C": 1.0}
#   model_ratings = {"A": 9.0, "B": 5.0, "C": 1.0}   (same rank order, different magnitudes)
#   Assert spearman_rho(true_ratings, model_ratings) == 1.0

# test_spearman_inverse:
#   model_ratings = {"A": 1.0, "B": 2.0, "C": 3.0}   (reversed order)
#   Assert spearman_rho(...) == -1.0

# test_spearman_partial:
#   5 teams; model recovers 4/5 pairwise relations correctly.
#   Assert spearman_rho(...) > 0.8  (directionally correct but imperfect).

# test_centered_rmse_zero_after_shift:
#   true_ratings  = {"A": 0.5, "B": -0.5}
#   model_ratings = {"A": 2.5, "B":  1.5}   (identical shape, shifted +2.0)
#   After centering both, each becomes [0.5, -0.5] → RMSE = 0.0.

# test_centered_rmse_compressed_signal:
#   true_ratings  = {"A": 1.0, "B": 0.0, "C": -1.0}
#   model_ratings = {"A": 0.5, "B": 0.0, "C": -0.5}   (compressed by 0.5×)
#   Centered RMSE = sqrt(mean([0.25, 0.0, 0.25])) = sqrt(0.25/2 * 2) = 0.5  [verify by hand]
#   Assert abs(centered_rmse(...) - 0.5) < 1e-9

# test_tier_accuracy_perfect_matching_labels:
#   true_tiers  = {"A": 1, "B": 1, "C": 2, "D": 2}
#   model_tiers = {"A": 1, "B": 1, "C": 2, "D": 2}
#   Assert tier_accuracy(...) == 1.0

# test_tier_accuracy_relabeled_flip:
#   true_tiers  = {"A": 1, "B": 1, "C": 2, "D": 2}
#   model_tiers = {"A": 2, "B": 2, "C": 1, "D": 1}   (tier labels 1↔2 swapped)
#   Assert tier_accuracy(...) == 1.0 under best permutation

# test_tier_accuracy_partial:
#   4 teams; model correctly places 3; one mislabelled.
#   Assert tier_accuracy(...) == 0.75

# test_no_true_tiers_returns_zero:
#   ground_truth all have tier=None.
#   MetricsResult.tier_accuracy == 0.0, n_tiers_scored == 0.

# test_score_model_end_to_end:
#   Build a 6-team world via simulate() — 3 strong (attack=1.5, defense=0.5, tier=1)
#   and 3 weak (attack=0.5, defense=1.5, tier=2). Repeat round-robin 4 weeks; seed=42.
#   Run bespoke.rate() (flat solve). Call score_model(dataset.ground_truth, result).
#   Assert result.n_teams == 6.
#   Assert result.spearman_rho > 0.7   (model recovers strong-vs-weak direction).
#   No assertion on tier_accuracy (flat rate() emits empty tiers → n_tiers_scored == 0, ok).
```

### Step 2 — implement `harness/metrics.py` to green

Write functions top-down in the order the tests need them:

1. `spearman_rho(true_ratings: dict[str, float], model_ratings: dict[str, float]) -> float`
   — intersect keys, rank both via `numpy.argsort(argsort(v))` (dense ranks), `numpy.corrcoef`.
2. `centered_rmse(true_ratings: dict[str, float], model_ratings: dict[str, float]) -> float`
   — intersect keys, center each, compute `numpy.sqrt(numpy.mean((a - b)**2))`.
3. `tier_accuracy(true_tiers: dict[str, int], model_tiers: dict[str, int]) -> float`
   — intersect keys, enumerate label permutations via `itertools.permutations`, return max fraction.
4. `score_model(ground_truth: list[TeamParams], result: RateResult) -> MetricsResult`
   — build dicts from ground_truth, call the three functions, return frozen `MetricsResult`.

Run `pytest harness/ -q` and `ruff check .` before declaring green.

---

## Acceptance / Definition of done

- [ ] `harness/test_metrics.py` — all unit tests and the end-to-end test green.
- [ ] `harness/metrics.py` — `MetricsResult`, `score_model`, `spearman_rho`, `centered_rmse`,
      `tier_accuracy` all importable from the module.
- [ ] `pytest harness/ -q` — no regressions in `harness/test_harness.py`; the new tests pass.
- [ ] `ruff check .` clean.
- [ ] PR body: plain-English description of the `score_model` interface (what goes in, what
      comes out), the centering rationale, the permutation approach for tier labels, and the
      end-to-end test numbers (spearman_rho value for the 6-team fixture).

No `invariant-auditor` or `spec-keeper` run required — metrics are pure output consumers;
they do not touch the model core, the fairness floor, or any data path that feeds back into a solve.

---

## Out of scope

- Kendall τ — Spearman ρ only for Stage A.
- MAE — RMSE only; MAE is a one-liner add if TASK-12 needs it.
- TASK-12's comparison runner (`harness/run.py`, `reports/`) — this task only builds the
  module; TASK-12 calls `score_model` from it.
- Scenario-specific rank-recovery assertions — those live in the scenario files (TASK-11 done).
- Trend/momentum scoring (e.g. spearman on trend vs true trajectory slope) — out of scope for
  Stage A; add in Stage B if needed.
- Any change to models, generator, harness invariants, or adapters.
