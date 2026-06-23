# TASK-06: Trend + recency weighting (I11)

**State:** ready · **Model:** opus — model core (`models/bespoke.py` solve/aggregate), the recency
aggregate and the trend output. This is the third link in the sequential core-model chain.
**Owns (files):** `models/bespoke.py`, `models/test_bespoke_rate.py` (extend),
`models/test_bespoke_trend.py` (new).
**Parallel-safe:** no — owns `models/bespoke.py` (the core). Never run beside any other core task.
**Depends on:** TASK-01 (done), TASK-05 (done — `rate_weekly` + the frozen-tier window this builds on).
**Branch from:** latest `main` (currently `093614a`) — the `/task 06` loop handles branch + PR.

---

## Goal

Bring the model's two recency-driven behaviours online: **(1) recency-weighted aggregation** — each
game's contribution to a team's rating is weighted by `w_g = exp(-ρ·(now − week_g))` so recent games
dominate (memo §2, brief §1.7), and **(2) the trend/momentum output** — populate `RateResult.trend`
with each team's rating slope over recent weeks so a rising team is visibly distinguished from a
flat-but-equal-rating team (memo §6, brief §1.7). Prove invariant **I11**: two teams with equal
season-average true strength but opposite trajectories (one rising, one falling) get **distinct trend
signs**, and recency weighting makes their point-in-time ratings reflect current form.

This is what the TASK-05 hand-off flagged: until recency weighting lands, the cumulative solve makes a
one-week blip a *permanent step* in the per-week tier rather than a transient. With `w_g` in the
aggregate, an old blip game is down-weighted as weeks advance, so blips **decay** — the secondary
payoff of this task (the I13 story stops needing the frozen-read-only framing).

---

## Read first (in this order — a cold chat must absorb all of these)

1. **`CLAUDE.md`** — prime directive (100% AI-authored, reviewed in chat), TDD rule, the invariant
   gate, determinism is sacred (I8), observed-vs-derived wall, the fairness floor is structural.
2. **`docs/planning/operating-model.md`** — task template, the opus model-core rule, trunk + PR loop,
   the verification agents (`invariant-auditor`, `spec-keeper`) you must run before the PR.
3. **`docs/analysis/decision-memo.md`**:
   - **§2** — the aggregation formula `r_i ← (1−λ)·Σ_g w_g·credit_g / Σ_g w_g + λ·r̄`, with
     `w_g = recency(week_g)`, `recency(week) = exp(−ρ·(now−week))`. **This is the formula you are
     implementing — the solve currently uses a plain (uniform) mean.**
   - **§3** — determinism/convergence/uniqueness (I8/I9). Recency weights are fixed non-negative
     per-game scalars, so they don't enter the `α` coupling: the contraction argument is unchanged.
   - **§6** — the momentum/trend output: `trend` = slope of the recency-weighted rating over the last
     few weeks (OLS slope of `r_i(week)`, or `r_recent − r_baseline`). The tier `consistency` measure
     (§5, already built in TASK-05) feeds the same trend/confidence story.
   - **§7 / §8** — `perGameAttribution` returns the named drivers **plus `w`** (the recency weight)
     per game. The interface (§8) lists `perGameAttribution:{game->{base,marginAdj,scheduleTerm,w}}`.
   - **§9** — strawman defaults: `ρ` (game recency) is "exp decay, ~½-life 3–4 weeks"; `ρ_tier = ρ`.
   - **§10** — invariant map, **I11 row** ("trend = slope of recency-weighted rating (§6)").
4. **`docs/knowledge-bank/rating-model-test-brief.md`** §1.7 (recency weighting + first-class
   momentum/trend), §4 I11 ("a team on a rising true-strength trajectory shows a positive trend signal
   distinct from a flat-but-equal-rating team"), §7 **scenario 11** ("two teams, equal season-average
   true rating, one rising / one falling within the season; assert I11 and that recency weighting
   reflects current form"), §5 (Level-0 only — `week` drives recency; never feed a derived value back in).
5. **`models/bespoke.py`** — the full file. The pieces you touch:
   - `CreditBreakdown` — add a `w: float = 1.0` field (the recency weight). `total` stays
     `base + margin_adj + schedule_term` (it is the *credit*, NOT credit×weight) — do not change it.
     The default keeps every existing construction site valid.
   - `_Entry` — currently `(base, raw_margin, opp_id, result)`. **Add the game's `week`** so the solve
     can compute `w_g`. Update `_build_entries` (both perspectives) and the canonical sort key.
   - `_solve` / `_attribute` — currently a **uniform** mean `total/len(ent)`. Change to the
     **recency-weighted** mean `Σ w_g·(base+margin+α·r_opp) / Σ w_g`, with `w_g = exp(−ρ·(now−week_g))`.
     `now` is the latest week present in that solve's entries. Re-centering stays as is.
   - `_attribute` — record `w` on each `CreditBreakdown`, and make the reconciliation use the
     **weighted** mean so `rating_i == (1−λ)·(Σ w_g·total_g / Σ w_g) − center_offset` is exact (memo §7).
   - `rate()` — the flat baseline. **Pass `ρ = 0`** here so all `w_g = 1` → the weighted mean reduces
     to the current uniform mean → **byte-identical** output → all existing `rate()` tests (I8/I9 and
     the credit/cross-opponent reconciliation) stay green unchanged. State this in a comment.
   - `rate_weekly()` — the tier-aware per-week solve. Add a `rho` (game recency) parameter
     (default per §9, see "Architecture decisions" below). For each week W's solve, `now = W`, so
     `w_g = exp(−ρ·(W − week_g))` — an older game is down-weighted relative to the week being solved.
     After the walk, populate `RateResult.trend` (see below).
   - `RateResult.trend` — currently `{}`; this task fills it.
6. **`models/test_bespoke_rate.py`** — existing `rate()` I8/I9 tests AND the `rate_weekly` I13 tests
   from TASK-05. The `rate()` tests must stay **byte-identical** (ρ=0 path). The `rate_weekly` I13
   tests are **inequality-based** (e.g. `|swing_w1| > |swing_w4|`); recency weighting shifts the
   numbers but the inequalities must still hold — **re-run and confirm**, do not weaken an assertion.
7. **`models/test_bespoke_credit.py`** and **`models/test_bespoke_cross_opponent.py`** — must stay
   green (they exercise `per_game_credit` / `rate`, both on the ρ=0 / uniform path).
8. **`generator/simulate.py`** — `TeamParams(trajectory=...)` supports `"rising"`, `"falling"`,
   `"flat"`, `"blip@wN"` (`_TRAJ_STEP = 0.05` attack drift/week). `week_params(team, week)` is
   **exported** so a test can reconstruct per-week true ratings for the I11 scenario without re-running
   the generator. `WorldConfig` / `Matchup` / `simulate` are the construction API (see the existing
   `round_robin_dataset` helper at the top of `test_bespoke_rate.py`).

---

## Architecture decisions (settled by the memo/brief — do not re-debate)

**Recency weight.** `w_g = exp(−ρ·(now − week_g))`, `ρ ≥ 0`, `now` = the latest week in the solve's
entry set. ρ=0 ⇒ uniform (the flat baseline). The per-game weight is a fixed non-negative scalar
applied inside the per-game average; it multiplies the *whole* credit `(base + margin_adj + α·r_opp)`,
so it never touches `base`'s role as a floor (the floor is about ordering *within* a game, which
weighting can't disturb) and never enters the `α` cross-team coupling — the §3 contraction proof
(Banach, `k<1`) is unchanged. Determinism (I8): weights are pure functions of `week`, no RNG.

**`rho` default in `rate_weekly`.** Use **`rho = 0.2`** (~3.5-week half-life), matching memo §9
(`ρ` ≈ ½-life 3–4 weeks) and the `rho_tier = 0.2` already shipped in TASK-05 (memo §9: `ρ_tier = ρ`).
Keep it a parameter (Stage A/B sweeps `ρ`). Do **not** use a 1.0 placeholder — at a ~1-week half-life
recent games swamp everything and the trend window collapses; the gentler decay is what lets a rising
trajectory register as a *slope* rather than a single-week jump.

**Trend signal (`RateResult.trend`).** In `rate_weekly`, record each team's converged rating per week
(you already converge `ratings` for "all games through week W" — capture `ratings[t]` into a per-team
series keyed by W). After the walk, `trend[t]` = the **OLS slope** of that team's rating series over
the last `trend_window` weeks (default `trend_window = 4`, a parameter). Determinism: ordinary least
squares on a fixed (week, rating) series — closed form, no RNG, stable team order (I8). A team with a
single recorded week (or zero variance in weeks) gets `trend = 0.0`. Document the choice of OLS-slope
over `r_recent − r_baseline` (OLS uses the whole window, less jumpy; both are sanctioned by §6).

**`w` in attribution.** Add `w: float = 1.0` to `CreditBreakdown`; `_attribute` sets it to the game's
recency weight. This is the §8 interface's fourth attribution term and the §7 explainability promise
("recent games carried more"). The reconciliation identity becomes the **weighted** mean — update it
and any reconciliation assertion to divide by `Σ w_g`, not `len(ent)`.

**Scope wall (observed vs derived, brief §5).** `week` is a Level-0 field (`GameRow.week`) — using it
for recency is reading an *observed* input, not feeding a derived value back in. Trend is an *output*
only; it never re-enters the solve. Keep it that way.

---

## TDD approach — write the tests first, watch them fail, then implement

### Step 1 — `models/test_bespoke_trend.py` (new; the I11 proof)

Build a multi-week dataset with the generator. Mirror `round_robin_dataset` in
`test_bespoke_rate.py` for the construction pattern.

```python
# test_recency_weight_is_uniform_when_rho_zero:
#   rate(games) is byte-identical with the new code path — ρ=0 ⇒ all w_g=1 ⇒ uniform mean.
#   (Guards the "flat baseline unchanged" promise; compare rate(games).ratings to a saved expectation
#    or simply assert rate() still satisfies its existing centering/recovery tests.)

# test_attribution_exposes_recency_weight:
#   rate_weekly(...).per_game_attribution[t][i].w is in (0, 1], and equals 1.0 for the most recent
#   week's games in the final solve (now == that week → exp(0) == 1).

# test_reconciliation_uses_weighted_mean:
#   For rate_weekly output, rating_t == (1-lam)*(Σ w_g·total_g / Σ w_g) - center_offset, within tol,
#   for every team (memo §7 made weight-aware).

# test_I11_rising_and_falling_have_opposite_trend_signs:
#   Two teams RISER (trajectory="rising") and FALLER (trajectory="falling") built symmetric around a
#   shared baseline so their season-AVERAGE true rating is equal (use week_params to confirm the
#   averages match), plus a stable FIELD they both play each week over ~6 weeks.
#   Assert: trend[RISER] > 0 > trend[FALLER].

# test_I11_recency_reflects_current_form:
#   Same dataset. Despite equal season-average true strength, RISER's final point-in-time rating
#   exceeds FALLER's (recency weighting surfaces current form), i.e. ratings[RISER] > ratings[FALLER].
#   Contrast: a uniform-weight solve (rate(), ρ=0) over the same games ranks them ~equal — show the
#   recency path separates them and the flat path does not (|Δ_weekly| > |Δ_flat|).

# test_trend_flat_for_steady_team:
#   A team with trajectory="flat" across the window has trend ≈ 0 (|trend| below a small epsilon).
```

### Step 2 — `models/test_bespoke_rate.py` (extend; recency makes blips decay)

```python
# test_blip_decays_in_per_week_tier_with_recency:
#   Using a blip@wN opponent (as in TASK-05's I13 scenario), reconstruct the opponent's per-week
#   FINALIZED tier across the season. With recency weighting, the blip-week's inflated games are
#   down-weighted in later weeks, so the opponent's per-week tier returns toward its baseline AFTER
#   the blip (a transient), not a permanent step. Assert the post-blip tier is closer to the
#   pre-blip baseline than to the blip-week tier. (This is the behaviour the TASK-05 hand-off said
#   recency would unlock.)

# Re-run the existing rate_weekly I13 tests and confirm the inequalities still hold with recency on.
```

### Step 3 — implement to green

Implement `w` on `CreditBreakdown`, `week` in `_Entry`, the weighted mean in `_solve`/`_attribute`,
the ρ=0 path in `rate()`, and `rho`/`trend_window` + the trend computation in `rate_weekly()`.
Run `pytest -q` and `ruff check .` before the PR.

---

## Acceptance / Definition of done

- [ ] `models/test_bespoke_trend.py` — all new I11 + recency tests green.
- [ ] `models/test_bespoke_rate.py` — new blip-decay test green; existing `rate()` I8/I9 tests
      **byte-identical**; existing `rate_weekly` I13 inequalities still hold (re-run, do not weaken).
- [ ] `models/test_bespoke_credit.py` and `models/test_bespoke_cross_opponent.py` — all still green.
- [ ] `RateResult.trend` is populated by `rate_weekly` (non-empty, one entry per team);
      `CreditBreakdown.w` populated in attribution and surfaced per the §8 interface.
- [ ] `ruff check .` clean.
- [ ] Run **`invariant-auditor`** against `models/bespoke.py` (focus I8/I9 unchanged, I11 new,
      I1/I4/I7 not regressed by weighting). Include its verdict in the PR.
- [ ] Run **`spec-keeper`** (watch for: recency touching `base`; double-counting opponent strength;
      determinism; derived data — trend — re-entering the solve). Include its verdict in the PR.
- [ ] PR body: plain-English summary leading with *why* and *what behaviour changed*, the invariants
      satisfied and how (cite I11/§6, I8/§3 unchanged, the structural floor untouched), the test
      evidence, and the I11 numbers (rising vs falling trend signs + the recency separation Δ).

---

## Out of scope

- Tier detection / the frozen-tier window — shipped in TASK-05; only *read* it here.
- Stage-A/B tuning of `ρ`, `trend_window`, or the half-life — defaults only; tests are the guardrail.
- The model-agnostic invariant harness (TASK-07) and truth-scoring metrics (TASK-10) — `trend` is an
  output this task populates; *scoring* I11 rank/trend recovery lives in those tasks.
- Running the full §7 scenario suite end-to-end, including Scenario 11 as a harness scenario — TASK-11.
- Any change to benchmarks, generator, or the JSON serialization.
