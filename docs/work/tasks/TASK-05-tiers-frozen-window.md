# TASK-05: Tiers + frozen window (I13)

**State:** ready · **Model:** opus — model core, convergence, fairness invariant.
**Owns (files):** `models/bespoke.py`, `models/tiers.py` (new), `models/test_tiers.py` (new),
`models/test_bespoke_rate.py` (extend).
**Parallel-safe:** no (owns `models/bespoke.py`). **Depends on:** TASK-01 (done).
**Branch from:** latest `main` — the `/task 05` loop handles branch + PR.

---

## Goal

Wire up the frozen-tier window (memo §5) so `rate()` / `rate_weekly()` populates
`RateResult.tiers` and the tier modulator `m(tier) / p(tier)` actually scales `marginAdj`.
Prove invariant I13 (anti-whipsaw): a one-week tier blip in an opponent causes a bounded, damped
swing in the credit it confers when a ≤4-week recency-weighted frozen window is used, while a
single-week window whipsaws. This is the determinism + fairness guarantee for the frozen-tier design.

---

## Read first (in this order — a cold chat must absorb all of these)

1. **`CLAUDE.md`** — prime directive, TDD rule, invariant gate, no derived inputs as model inputs.
2. **`docs/planning/operating-model.md`** — task template, opus-model rule, trunk + PR.
3. **`docs/analysis/decision-memo.md`** §1.2 (`marginAdj`, the `m(tier)/p(tier)` modulators),
   §4 (tier detection: natural gaps, `tierCount: "auto"`, model-selection rule), §5 (frozen-tier
   window: recency-weighted read over ≤4 prior weeks, `consistency` measure, cold start),
   §10 invariant map (I13 row), §11 Q3 decision (discrete tier lookup, orthogonal channels).
4. **`docs/knowledge-bank/rating-model-test-brief.md`** §1.6 (tier × margin interaction rule),
   §1.8 (frozen window, consistency, cold start), §4 I13 (the invariant statement), §7 scenario 13
   (the blip test: sweep window 1→4, show single-week freeze whipsaws).
5. **`models/bespoke.py`** — full file. Pay attention to:
   - `BespokeParams` (add `tier_m` / `tier_p` / `tier_default_m` / `tier_default_p` here)
   - `base_and_margin()` — does NOT use tier; tier modulation is applied on top
   - `per_game_credit()` — already accepts `opp_tier` but currently ignores it; TASK-05 wires it in
   - `entries` dict in `rate()` stores `(base, margin, opp_id)` — see note below on how to extend
   - `RateResult` — `tiers` and `trend` are currently empty dicts; populate `tiers` here
6. **`models/test_bespoke_credit.py`** — existing I1–I5 credit tests. Must stay green. They call
   `per_game_credit(..., opp_tier=3, ...)` — design the tier-3 modulator to be the neutral
   baseline (`m=1.0, p=1.0`) so these tests pass unchanged.
7. **`models/test_bespoke_cross_opponent.py`** — I6/I7/I10/I12 tests. Must stay green.
8. **`models/test_bespoke_rate.py`** — existing I8/I9/convergence tests. Must stay green; you will
   add I13 tests to this file.

---

## Architecture decisions (do not re-debate these — memo and brief settle them)

**Tier detection (`models/tiers.py`):**
- `detect_tiers(ratings: dict[str, float], tier_count: int | str = "auto") -> dict[str, int]`
  Sort teams by descending rating. Compute gaps between consecutive sorted ratings. With
  `"auto"`: split wherever `gap > c * median_gap` (reasonable default: `c = 2.0`; keep it a
  parameter). Return a 1-indexed tier dict (`{team_id: tier_int}`). Tier 1 = top.
- `tierCount` as integer: place exactly N−1 cuts at the N−1 largest gaps. Raise if fewer than
  N distinct values.

**Frozen-tier window (`models/tiers.py`):**
- `class TierWindow` — accumulates finalized tier dicts week-by-week (up to `max_weeks` = 4).
  ```
  TierWindow.add_week(week: int, tiers: dict[str, int]) -> None
  TierWindow.frozen_tier(team_id: str, rho: float = 1.0) -> float | None
      # recency-weighted mean of tier across stored weeks:
      # weight_w = exp(-rho * (current_week - w))   (current_week = latest stored week)
      # returns None if no history yet (cold-start: caller uses tier-agnostic path)
  TierWindow.consistency(team_id: str) -> float
      # 1 - (weighted std of tier / max_possible_std)
      # A team seen in only one tier → 1.0; maximally bouncing → 0.0.
  ```

**Tier modulators in `BespokeParams`:**
Add to `BespokeParams`:
```python
tier_m: tuple[float, ...] = (1.3, 1.15, 1.0, 0.85)   # indexed by tier-1; tier 3 = 1.0 (neutral)
tier_p: tuple[float, ...] = (0.7, 0.85, 1.0, 1.15)   # indexed by tier-1; tier 3 = 1.0 (neutral)
tier_default_m: float = 0.7    # for tiers beyond the table (deep field)
tier_default_p: float = 1.3    # for tiers beyond the table (deep field)
```
Helper: `params.m_for(tier_float: float) -> float` — round `tier_float` to nearest int, clamp to
table length, return the modulator. Same pattern for `p_for`. Tier 3 must always return 1.0 for
both so existing credit tests are unchanged.

**Wiring `opp_tier` into `per_game_credit`:**
`per_game_credit` currently accepts `opp_tier` but does not use it. Wire it:
```python
result = classify(goals_for, goals_against)
base, raw_margin = base_and_margin(goals_for, goals_against, params)
if result == "W":
    margin_adj = raw_margin * params.m_for(opp_tier)   # scale the bonus
elif result == "L":
    margin_adj = raw_margin * params.p_for(opp_tier)   # scale the penalty (raw_margin <= 0)
else:
    margin_adj = 0.0                                   # ties: no change (I5)
```
Structural guarantees preserved:
- `m_for(tier) >= 0` and `p_for(tier) >= 0` — sign of `marginAdj` never flips → I4 holds.
- `base` is never touched → I1, I7 hold structurally.
- Existing tests use `opp_tier=3` → `m_for(3) = 1.0`, `p_for(3) = 1.0` → no change.

**`entries` dict in `rate()`:** currently stores `(base, margin, opp_id)`. For the tier-aware
solve you need the result classification too. Add it: store `(base, raw_margin, opp_id, result_str)`
where `result_str ∈ {"W", "T", "L"}`. Update both the build loop and the attribution pass.
This change to `rate()` must not break existing tests — verify by running them.

**`rate_weekly(games, params, config)` — the new tier-aware entry point:**
Keep the existing `rate()` as-is (no tiers, single-pass); it remains valid for existing tests and
as a flat baseline. Add `rate_weekly()`:
```python
def rate_weekly(
    games: Iterable[GameRow],
    params: BespokeParams | None = None,
    *,
    tier_count: int | str = "auto",
    gap_c: float = 2.0,
    max_window: int = 4,
    rho_tier: float = 1.0,
    lam: float = 0.05,
    tol: float = 1e-12,
    max_iter: int = 1000,
) -> RateResult:
```
Algorithm:
1. Group games by week. Sort weeks ascending (deterministic — stable sort on week number then
   team id, I8).
2. Initialise `window = TierWindow(max_weeks=max_window)`.
3. For each week W in order:
   a. `frozen = {team: window.frozen_tier(team, rho=rho_tier) for team in all_teams}`
      (None → cold-start, treat as tier-agnostic: `m_for=1.0, p_for=1.0`)
   b. Run the fixed-point solve on **all games through week W** (not just week W's games), applying
      the frozen tier modulator: replace `(base + raw_margin)` in the solve with
      `base + scaled_margin(raw_margin, frozen[opp], result, params)`. This is the
      **per-week solve**: same contraction proof holds (modulators are non-negative scalars, they
      don't alter the spectral radius argument in memo §3).
   c. Run `detect_tiers()` on the converged ratings for week W.
   d. `window.add_week(W, tiers_W)`.
4. Return `RateResult` with `ratings`, `tiers` (from the last week's `detect_tiers`),
   `per_game_attribution`, `trend={}` (TASK-06 will fill this), `center_offset`.

Cold-start: weeks 1–2 have no usable window; `frozen_tier()` returns `None` → m=p=1.0 (tier-agnostic
pass). Window activates from week 3 onward (or when ≥2 finalized weeks exist, whichever comes first).
State this as a comment in the code.

---

## TDD approach — write tests first, watch them fail, then implement

### Step 1 — `models/test_tiers.py` (new file, before writing `models/tiers.py`)

```python
# test_detect_tiers_splits_on_known_gap:
# Ratings: A=1.0, B=0.9, gap=0.1, then C=0.0, D=-0.1. Big gap between B and C.
# With auto mode and c=2.0: only the 0.9-gap between B(0.9) and C(0.0) should cut.
# Expect: A,B → tier 1; C,D → tier 2.

# test_detect_tiers_integer_count:
# Same ratings, tierCount=3: three tiers. The two largest gaps are used.

# test_detect_tiers_single_tier_fallback:
# All ratings within median_gap range: no cut found → everything in tier 1.

# test_tier_window_cold_start_returns_none:
# Empty TierWindow: frozen_tier("X") is None.

# test_tier_window_single_week:
# After add_week(1, {"A": 2, "B": 3}), frozen_tier("A") ≈ 2.0 (exact, only one week).

# test_tier_window_damps_blip:
# Weeks 1,3,4: team X is tier 3. Week 2: tier 1 (blip).
# After all four weeks, frozen_tier("X") should be much closer to 3.0 than 1.0.

# test_consistency_stable_team:
# Same tier every week for 4 weeks → consistency ≈ 1.0.

# test_consistency_volatile_team:
# Tiers alternate 1,4,1,4 over 4 weeks → consistency < 0.5.
```

### Step 2 — `models/test_bespoke_rate.py` (extend with I13 tests)

```python
# test_rate_existing_passes_unchanged:
# Run all existing tests to confirm `rate()` is untouched.

# test_tiers_populated_by_rate_weekly:
# rate_weekly() on a multi-week dataset returns RateResult with non-empty tiers dict.
# Every team that appears in the games has a tier entry.

# test_I13_blip_bounded_with_4week_window:
# Construct a 5-week dataset (using generator with WorldConfig):
#   - Teams: ELITE (strong), BLIP (normally tier-2 but gets a tier-1 run in week 2 only), FIELD (weak)
#   - SUBJECT plays BLIP in week 1 and week 4.
#   - Compare SUBJECT's credit for beating BLIP in week 1 (pre-blip) vs week 4 (post-blip, window=4).
#   - With window=4, BLIP's frozen tier in week 4 should reflect ~3 weeks of tier-2 + 1 week of tier-1
#     → the credit SUBJECT earns for week 4's win over BLIP should be close to week 1's credit.
#   - Formally: |credit_w4 - credit_w1| < |credit_if_blip_frozen_as_tier1 - credit_w1|.
#   This proves the window damps the blip.

# test_I13_single_week_window_whipsaws:
# Same scenario but max_window=1. BLIP's frozen tier in week 3 is tier-1 (only last week's tier = blip).
# The credit swing is larger than with window=4.
# Formally: |swing_window1| > |swing_window4|.

# test_I13_consistency_low_for_volatile_opponent:
# After the blip scenario (4 weeks), window.consistency("BLIP") < 0.5 (it bounced tiers).

# test_tier_modulator_scales_adjustment_not_base:
# Against a tier-1 opponent, per_game_credit win earns more (m > 1.0) than vs tier-3.
# Against a tier-1 opponent, per_game_credit loss earns more (penalty softened, p < 1.0) than vs tier-3.
# The base is identical in both cases (I1/I7 not touched).
```

### Step 3 — Implement `models/tiers.py`, then update `models/bespoke.py`

Implement the tests above to green. Run `pytest -q` and `ruff check .` before the PR.

---

## Acceptance / Definition of done

- [ ] `models/test_tiers.py` — all new tests green.
- [ ] `models/test_bespoke_rate.py` — I13 tests green; existing I8/I9 tests still green.
- [ ] `models/test_bespoke_credit.py` — all existing I1–I5 tests still green (tier-3 = neutral).
- [ ] `models/test_bespoke_cross_opponent.py` — all existing I6/I7/I10/I12 tests still green.
- [ ] `ruff check .` clean.
- [ ] Run **`invariant-auditor`** agent against `models/bespoke.py` after changes. Include its verdict in the PR.
- [ ] Run **`spec-keeper`** agent. Include its verdict in the PR.
- [ ] PR body: plain-English summary of what changed, which invariants are satisfied and how,
      the test evidence, and the I13 numbers (blip swing with window=1 vs window=4).

---

## Out of scope

- Recency weighting of game credits (`w_g = exp(−ρ·Δweeks)`) — that's TASK-06.
- Trend / momentum signal (`RateResult.trend`) — that's TASK-06.
- Full scenario suite, including running Scenario 13 end-to-end — that's TASK-11.
- Stage-B tuning of the modulator table or window parameters.
- Dixon–Coles correction in the generator — that's TASK-08.
- Any harness or metrics changes.
