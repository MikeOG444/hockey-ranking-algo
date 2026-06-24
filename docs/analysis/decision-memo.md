# Decision Memo — Bespoke Rating Model Design

**Phase 0 deliverable. Gate for all solver work.** Status: **DRAFT for owner review.**
Resolves the brief's open tensions into concrete math so we don't build the wrong thing.

This memo's job: give every invariant **I1–I13** a named mechanism, and prove the central tension
(principles 6/7 vs 1/4/5) cannot break, with a worked numeric example. Defaults here are the §3a
strawman starting point — *to be tuned in the build, not final.*

---

## 0. Notation

- Teams `i`. Rating `r_i ∈ ℝ`, centered so `mean(r)=0` (ratings are relative).
- A game `g = (i, j, gf, ga, week)`: team `i` scored `gf`, opponent `j` scored `ga`. Outcome inferred.
- `margin = gf - ga`. **Bucket** `B(margin)`: close=`|margin|∈{1,2}`, then `3`, `4`, `5+`.
- `tier(j, week)` = opponent `j`'s **frozen** tier this week (from the ≤4-week window, §5).
- `R_j` = opponent `j`'s **current** rating (the floating schedule signal).

---

## 1. The central tension and its resolution

> Principles 6/7 (opponent/margin/momentum-aware, floating) push toward a model that *can* drop you for
> underperformance. Principles 1/4/5 forbid that from ever flipping result order. (Brief §1.)

**Resolution = additive decomposition with a structural floor.** Per-game credit is three independent terms:

```
credit(g) =  base(result)                       # FLOOR. result ∈ {W,T,L}.  W > T > L.
           + marginAdj(result, B, tier(j))      # win: bonus ≥ 0 ; loss: penalty ≤ 0 ; tie: 0
           + scheduleTerm(R_j, result, B)        # the ONLY cross-opponent signal
```

The key move: **`base` depends on result and nothing else.** No tier, margin, momentum, or opponent
input can touch it. Modulation is confined to `marginAdj` (and the schedule term, which is about a
*different* opponent). This makes the fairness invariants **structural**, not emergent — they hold by the
*shape* of the formula, not by lucky parameter values.

### 1.1 `base` — the result quality (I1, I5)
```
base(W) = W,  base(T) = T,  base(L) = L,   with  W > T > L.
```
> **Superseded by TASK-17 (§3.1).** The strawman magnitudes were `3 / 1 / 0` (an absolute floor); they are
> now **centered** to `0.5 / 0.0 / -0.25`, and the fairness floor moved from `base`'s magnitude to the
> per-game **win-floor** (`credit = max(raw, own_rating)` for a win). `base` is now the *centered result
> quality* feeding the surprise, not an absolute floor. The same-opponent argument below still holds.

Against the **same opponent**, holding margin fixed, `credit(W) ≥ credit(T) ≥ credit(L)` because the
`base` gap dominates and `marginAdj`/`scheduleTerm` (and, post-TASK-17, `self_term`) are identical for the
same opponent+margin, and the win-floor only ever *raises* a win. → **I1, I5.**

### 1.2 `marginAdj` — bounded, signed, bucketed (I2, I3, I4)
```
WIN:   marginAdj = m(tier) · bonus[B]          bonus = {close:0, 3:b3, 4:b4, 5+:b5}
                                               with  b3 > (b4−b3) > (b5−b4) ≥ 0   (diminishing, capped)
                                               and   bonus[B] ≥ 0 always           (never punish a win)
LOSS:  marginAdj = −p(tier) · pen[B]           pen   = {close:0, 3:p3, 4:p4, 5+:p5},  pen increasing
                                               (close loss = 0 extra penalty; never positive)
TIE:   marginAdj = 0
```
- Wins: `bonus` is non-decreasing in margin and ≥0 → **I2**. The diminishing schedule `b3 > Δ4 > Δ5`
  caps blowout gain → **I3**.
- Losses: `pen[close]=0`, increasing after → a close loss is credited **≥** a 3+ loss, and since
  `marginAdj ≤ 0` for losses it can never lift a loss to/above a tie → **I4**.
- `m(tier) ≥ 0` and `p(tier) ≥ 0` are **tier modulators** (§4) — they scale the *bonus/penalty only*,
  so they can shrink/grow the adjustment but **never flip its sign and never touch `base`** → preserves
  ordering under expectation (**I7**).

### 1.3 `scheduleTerm` — the cross-opponent signal (I6, I10)
This is where "close loss to elite is positive / close win over weak is negative" lives. It depends on the
opponent's **current** rating `R_j` (floating, §5) — *not* the opponent's stale early rating → **I10**.
```
scheduleTerm = α · R_j                       # credit for the strength of who you played
```
**Two build-time corrections (2026-06-20), both to keep invariants structural:**
1. *Removed the `resultWeight(result, B)` factor* an earlier draft applied. It is **unsafe for I1**:
   against the same elite opponent (`scheduleTerm > 0`), a larger weight on a loss than a win adds *more*
   positive credit to the loss and can flip win/loss ordering.
2. *Replaced `α·(R_j − r_i)` with `α·R_j`* — dropped the own-rating self-reference. The `− r_i` term makes
   a team's rating appear inside its own credit; folded into the fixed-point solve it gives an iteration
   matrix with spectral radius `2α(1−λ)`, which **diverges for α ≳ 0.53** (right where I6 wants α). Plain
   `α·R_j` (standard strength-of-schedule) gives spectral radius `α(1−λ) < 1` for all α<1 → clean
   convergence (I9). It is also more faithful to principle 6, which speaks of *absolute* opponent tier
   ("a top team", "a weak team"), not strength relative to self.

> **TASK-17 note (§3.1):** TASK-17 reintroduces an own-rating term, but as a **separate, additive
> `self_term = +(1−α)·r_i`** — NOT by folding `−r_i` into the schedule term. The distinction is exactly
> what makes it safe: the rejected `α·(R_j − r_i)` form has self-coefficient **`−α`** (→ spectral radius
> `2α(1−λ)`, divergent); the TASK-17 form has self-coefficient **`+(1−α)`**, so the self-weight `(1−α)`
> and opponent-weight `α` form a **convex split** (sum 1) and the map contracts at `(1−λ)` for *any*
> α∈[0,1). The `scheduleTerm` itself is unchanged (`α·R_j`); the self-reference lives in its own channel.

Net effect: `scheduleTerm` is **identical for win/tie/loss vs the same opponent**, so it shifts
cross-opponent comparisons (I6/I10) **without ever affecting same-opponent ordering** (I1) — that
orthogonality is the whole trick. The I6 condition is unchanged (`α·(R_elite − R_field) > W − L`; the
`r_i` canceled in the §1.4 example). The close-vs-blowout nuance is carried by `marginAdj`, not the
schedule term. Verified by `models/test_bespoke_credit.py`.

### 1.4 Why I1 and I6 cannot collide — *worked example*

I6 (brief §82): *a 1-goal loss to a top-tier team must rate better than a 1-goal win over a
bottom-of-field team.* I1: *vs the same opponent, win ≥ tie ≥ loss.* These feel contradictory; they aren't,
because they compare **different things**.

Let strawman `W=3, T=1, L=0`, `marginAdj=0` for close games. The schedule term is plain `α·R_j` (the
§1.3 correction dropped the `− r_i` self-reference), so our own rating never enters our credit. Ratings
centered: elite team `R_elite=+4`, field team `R_field=−2`.

| Game | base | marginAdj | scheduleTerm = α·R_j | **credit (α=0.5)** |
|---|---|---|---|---|
| 1-goal **loss to elite** | `L=0` | `0` (close) | `0.5·4 = +2.0` | **+2.0** |
| 1-goal **win over field** | `W=3` | `0` (close) | `0.5·(−2) = −1.0` | **+2.0**… |

At `α=0.5` the canonical +4/−2 gap (6) is exactly a tie (`α·gap = 3 = W−L`), so I6 is not yet strict.
This *credit-level* worked example clears at any `α>0.5`. But whether the solver's *converged* ratings
actually reach a gap of 6 is topology-dependent: on the Scenario-7 league the centered spread reaches
only `≈4.38`, so end-to-end I6 needs `α ≳ 0.69` — which is why the **shipped default is `α=0.75`**
(TASK-13, validated end-to-end by Scenario 7). See §9 and Q1 for the full derivation.

Now check **I1 is untouched**: against *that same elite team*, compare a win vs a loss. Both share the
**same** `scheduleTerm` (`0.6·4 = +2.4`) and same close-`marginAdj` (0). Only `base` differs:
- win vs elite = `3 + 0 + 2.4 = 5.4`
- loss vs elite = `0 + 0 + 2.4 = 2.4`

`5.4 > 2.4` — **win still beats loss against the same opponent.** I6 moved the *cross-opponent* comparison
via `scheduleTerm`; I1 is governed by `base`, which I6's mechanism never touches. **Both hold simultaneously. ∎**

> This worked example is the single most important thing for the build to preserve. Any refactor of the
> credit function must reproduce this table.

---

## 2. Aggregation into a season rating

A team's rating is the recency- and schedule-weighted aggregate of its per-game credits, solved to a
fixed point (because `scheduleTerm` depends on opponents' ratings, which depend on theirs…):

```
r_i  ←  (1 − λ) · Σ_g w_g · credit_g(R)  /  Σ_g w_g     +     λ · r̄
                                                                ^^^ prior toward mean (r̄ = 0)
w_g = recency(week_g) · 1            # recent games heavier (principle 7); decay = exp(−ρ·Δweeks)
λ   = small regularization (e.g. 0.05)
```

- **Recency weighting** `recency(week)=exp(−ρ·(now−week))` makes recent games dominate → feeds momentum.
- **Regularization** `λ·r̄` (prior toward the mean) guarantees a unique fixed point even on
  disconnected/sparse graphs (scenarios 1, 2) — without it, isolated pods have a free additive constant.

---

## 3. Determinism, convergence, uniqueness (I8, I9)

**Within a week, tiers are frozen** (§5), so the only thing iterating is ratings → credit → ratings.
The update map `T(r)` above is, with `λ>0`, a **contraction** in the sup-norm: the `scheduleTerm`
coupling has Lipschitz constant `≤ α`, and the `λ·r̄` pull plus normalization keep `‖T(r)−T(r')‖ ≤ k‖r−r'‖`
with `k<1` for `α` in the usable range. Banach ⇒ **unique fixed point, reached from any start** → **I9**.

**Determinism (I8):** batch solve (no online/stochastic step), fixed iteration count or
`‖Δr‖<ε` tolerance, **stable sort on team id** for any ranking/tie-break, no RNG anywhere. Same games in
any input order → byte-identical output. We will *test* order-invariance by shuffling input rows.

> This is why the brief favors a convergent batch solve over Elo/Glicko (which are order-dependent and
> stochastic). Elo stays only as a benchmark.

### 3.1 TASK-17 addendum — surprise-centering supersedes the absolute `base` floor

**Why.** On real data the absolute `base = 3/1/0` floor over-credited cheap wins: beating a near-zero
team banked the full `base = 3`, so a team padding soft late wins (Woodbridge) out-ranked a team losing
honorably to elites (Mid-Fairfield) despite a 5-0 head-to-head. The floor *"a win must always count"* was
the wrong principle — beating an opponent you beat 99.99% of the time demonstrates no strength. The owner
reframed it to *"a win is not a loss"*: a win never *lowers* you, but an *expected* win is ~neutral.

**New credit (replaces the `base = 3/1/0` magnitudes; structure of §1 otherwise intact).** Per game,
from team *i* vs opponent *j*:

```
surprise = base_c + marginAdj + α·(r_j − r_i)          # base_c CENTERED: win=+0.5, tie=0, loss=−0.25
credit   = r_i + surprise                               # = base_c + marginAdj + α·r_j + (1−α)·r_i
         = max(raw, r_i)  for a WIN                      # the win-floor: a win never lowers you
```

So the credit anchors on the team's own rating `r_i` (the new `self_term = (1−α)·r_i`) and adds the
surprise of the result against this opponent. An *expected* win (`r_j ≪ r_i`) gives `surprise ≤ 0`, the
win-floor clamps the credit to `r_i` (neutral); a close loss to an elite (`r_j ≫ r_i`) gives a small
positive surprise. **I1 (same-opponent) is intact:** `r_i`, `self_term`, and `α·r_j` are identical across
W/T/L vs the same opponent, so the ordering is decided by `base_c(W) > base_c(T) > base_c(L)`, and the
win-floor only ever *raises* a win. **I6 is now robust** at every usable α — centering shrank the win/loss
quality gap from 3 to ~0.75, easily cleared by the converged spread (no α floor needed).

**Convergence re-derivation (the I9 obligation).** The damped update is `r_i ← (1−λ)·mean_g(credit_g) −
r̄`. For an unclamped game `credit_g = base_c + marginAdj + α·r_j + (1−α)·r_i`, so within one game the
self-coefficient `(1−α)` and the opponent-coupling `α` **sum to exactly 1**; for a clamped win
`credit_g = r_i` (self-coefficient 1, opponent-coupling 0) — still summing to 1. Hence every row of the
update's Jacobian has 1-norm `(1−λ)·1 = (1−λ)`, so `T` is a contraction with factor **`(1−λ)` for any
α ∈ [0, 1)** — *independent of α*, and strictly stronger than the old `α(1−λ)` bound. Banach ⇒ unique
fixed point from any start → **I9 preserved**. The fixed point is the Massey/Elo-style equilibrium
`r_i = ((1−λ)/λ)·mean_surprise_i` (your rating sits where your results stop surprising). Determinism (I8)
is unchanged: the self-anchor `r_i` is read from the previous iterate (Jacobi sweep), the clamp `max(·)`
is deterministic, no RNG.

**Channel orthogonality (no double-count).** `self_term = (1−α)·r_i` is the recentering *anchor*, not an
opponent-strength term — the two opponent-strength channels remain `scheduleTerm = α·r_j` and the tier
table, exactly as before. The reframe trades the floor's *absolute-level anchor* (which, on disconnected
synthetic graphs, ranked teams by accident) for honesty; see `reports/comparison.md` §4 for the resulting
synthetic rank-recovery cost and the pivot to real-data evaluation.

---

## 4. Tier detection (brief §2)

Each **finalized** week, derive tiers from natural gaps in that week's rating vector — **not hardcoded ranks.**

- **Default method (`tierMethod: "natural_gaps"`):** sort ratings, split at the largest gaps; choose the
  number of cuts `k` by a model-selection rule (gap must exceed `c · median_gap`, and/or 1-D k-means + BIC).
- **`tierCount: "auto"`** lets the rule pick `k`; an integer pins it; operator override allowed.
- Must reproduce the **observed shape** (knowledge-bank): isolated #1, tight #2–#11 cluster, minor seams
  ~#12–13, smooth field from ~#28. Expect ~3–5 meaningful bands + "the field." `k` is an **output**, not a constant.

`m(tier)` and `p(tier)` (the §1.2 modulators) are functions of the *opponent's* frozen tier: playing up a
tier raises the bonus ceiling / softens the loss penalty; playing down does the reverse — always on the
adjustment, never on `base`.

---

## 5. The frozen-tier window (brief §1.8) — the determinism + anti-whipsaw guarantee (I13)

**Within a week, the tiers used to credit that week's games are frozen from prior finalized weeks.** This
breaks the chicken-and-egg loop (never use this week's ratings to set this week's tiers) → guarantees
determinism. Across the season tiers still co-evolve, because each week builds on the converged output before it.

```
frozenTier(j, week) = recency-weighted read of j's finalized tier over the last ≤4 weeks
                       weights decay = exp(−ρ_tier·Δweeks)   (default ρ_tier = ρ, independently tunable)
consistency(j)      = 1 − normalized variance of j's tier across the window   ∈ [0,1]
confidence(j)       = g(consistency(j))    # a team bouncing tiers confers credit at lower confidence
```

- A one-week tier **blip** in `j` barely moves `frozenTier(j)` (it's averaged over ≤4 weeks, recency-decayed),
  so the credit `j` confers this week moves within a **bounded** amount → **I13**. A volatile `j` reads
  low `consistency`, which down-weights how much it can swing opponents' credit (anti-whipsaw).
- **Cold start:** weeks 1–2 have no usable window → run **tier-agnostic** (single provisional pass,
  `m=p=1`, no tier modulation). Frozen window activates once ≥2–3 finalized weeks exist. *Stated explicitly.*
- **Stage-B tunables (later):** window length (≤4), decay shape `ρ_tier`, and how strongly `consistency`
  modulates `confidence`. Scenario 13 sweeps window 1→4 to show single-week freeze whipsaws, windowed does not.

---

## 6. Momentum / trend output (I11)

Expose, alongside the point-in-time rating, a **trend signal** = slope of the team's recency-weighted
rating over the last few weeks (e.g. OLS slope of `r_i(week)` over the window, or `r_recent − r_baseline`).
Two teams with equal season-average rating but rising vs falling true strength get **distinct** trend
signs → **I11**. The tier `consistency` measure (§5) feeds the same trend/confidence output.

---

## 7. Explainability (I12)

`perGameAttribution` returns, per game, the named terms `{base, marginAdj, scheduleTerm, self_term}`
(TASK-17 added `self_term = (1−α)·own_rating`; for a floored win `total = max(raw, own_rating)`) and `w_g`. By
construction these **sum to the rating components** (within tolerance) → **I12**. The weekly delta
decomposes into **result-driven** (`Σ base+marginAdj` changes) vs **schedule-driven** (`Σ scheduleTerm`
changes from opponents re-rating). A hockey parent reads: *"your rating rose 1.2 — +0.8 from your own
results, +0.4 because the teams you beat got better."*

---

## 8. The common interface (all models implement)

```python
def rate(games: list[Level0Row], config: Config) -> RateResult:
    """
    games  : Level-0 rows only (week,date,time,team,opponent,goalsTeam,goalsOpponent). No derived inputs.
    config : tierCount('auto'|int), tierMethod, freezeWindowWeeks, decay/λ/α params.
    returns: ratings:{team->float}, tiers:{team->int}, perGameAttribution:{game->{base,marginAdj,scheduleTerm,w}},
             trend:{team->float}
    """
```
The MHR replica, ridge Massey, and bespoke all conform so the harness swaps them freely.

---

## 9. Defaults (Stage-A-tuned — TASK-13; floor reframed — TASK-17)

The shipped defaults below.

> **TASK-17 updates:** (1) `W/T/L` are now **centered** `0.5 / 0.0 / -0.25` (surprise-centering, §3.1) —
> the fairness floor moved to the per-game **win-floor**, so the magnitudes are no longer an absolute
> floor. (2) `α` is no longer derived from an I6 floor (centering made I6 robust at every α); it stays at
> the memo value `0.75`, and the synthetic `tune.py` sweep is **retired as the param-selection oracle**
> (the synthetic score was partly a floor artifact — evaluation pivots to real data, see
> `reports/comparison.md` §4). The bonus/penalty buckets, tier table, ρ, λ are unchanged.

The `α`/`ρ` picks are the **principled memo values** (formerly cross-checked by the rank-recovery sweep).

| Param | Default | Notes |
|---|---|---|
| `W / T / L` | `0.5 / 0.0 / -0.25` | **centered result quality (TASK-17, was `3/1/0`)**; fairness floor is now the per-game win-floor `max(raw, own_rating)`, structural — untuned |
| `bonus[3/4/5+]` | `0.6 / 0.9 / 1.0` | diminishing: `Δ=0.6,0.3,0.1`; close=0 (structural — untuned) |
| `pen[3/4/5+]` | `0.5 / 0.8 / 1.0` | close=0; increasing (structural — untuned) |
| `α` (schedule) | `0.75` | memo value. **TASK-17:** I6 no longer constrains α (centering made it robust at every α); `<1` keeps the I9 contraction — now `(1−λ)` *unconditionally* (§3.1), stronger than the old `α(1−λ)`. The old "re-derive α against the ≈4.38 gap" rationale (§11 Q1) no longer binds. |
| `m(tier)/p(tier)` | per-tier-gap scalars | modulate adjustment only (memo table unchanged; tier-strength sweep at ×2 did not help — orthogonal to α, Q3) |
| `ρ` (game recency) | `0.2` (exp decay, ~½-life 3–4 wks) | recent heavier; sweep pick, kept off 0 so I11 trend survives |
| `λ` (regularization) | `0.05` | unique fixed point (sets uniqueness not accuracy — untuned) |
| `freezeWindowWeeks` | `4` | ≤4; swept in Stage B |
| `ρ_tier` | `0.2` (`= ρ`) | follows `ρ` (memo §5) |

---

## 10. Invariant → mechanism map (the Phase-0 checklist)

| Inv | Guaranteed by |
|---|---|
| I1 ordering | `base` floor (§1.1), structural |
| I2 win-monotone | `bonus` non-decreasing, ≥0 (§1.2) |
| I3 blowout cap | diminishing `bonus` schedule (§1.2) |
| I4 close-loss floor | `pen[close]=0`, `marginAdj≤0` for losses (§1.2) |
| I5 tie placement | `base` gap + `marginAdj(tie)=0` (§1.1) |
| I6 tier×margin | `scheduleTerm` cross-opponent, worked example §1.4 |
| I7 underperformance no-flip | modulators touch adjustment only, never `base` (§1.2) |
| I8 determinism | batch solve, no RNG, stable sort (§3) |
| I9 convergence/uniqueness | contraction via `λ>0` (§3) |
| I10 stale-opponent float | `scheduleTerm` uses **current** `R_j` (§1.3) |
| I11 momentum | trend = slope of recency-weighted rating (§6) |
| I12 explainability | 3-term attribution sums to rating (§7) |
| I13 anti-whipsaw | recency-weighted ≤4-wk frozen window + consistency (§5) |

**Every invariant has a mechanism. The central tension has a worked counter-example. → Phase 0 exit met,
pending owner review.**

---

## 11. Resolved design decisions (assumptions to confirm by test)

**Decision criterion (ranked):** (1) invariant safety — never risk a fairness floor, structural > tuned;
(2) rank-recovery vs planted truth — the scoreboard; (3) explainability — a parent can read it, fewer knobs;
(4) robustness/determinism — insensitive to tier-boundary jitter and sparse graphs. Tie-break: fidelity to
brief intent. Every pick below is a **falsifiable assumption** with a named confirming scenario; the test,
not the pick, has the final word.

| # | Decision | Rationale (criterion) | Confirming test → *falsified if* |
|---|---|---|---|
| **Q1 `α`** | **SUPERSEDED by TASK-17 (§3.1):** centering shrank the W−L quality gap to ~0.75, so end-to-end I6 now holds at *every* α in the grid and no longer constrains α; the convergence bound is `(1−λ)` unconditionally (not `α(1−λ)`). The TASK-13 derivation below is kept as history (it was correct for the `3/1/0` floor model). — **RESOLVED (TASK-13): derived `α = 0.75`.** Re-derived against the solver's *reachable* converged spread, not the hand-picked +4/−2 example. On the Scenario-7 league the centered spread converges to `R_TOP − R_BOTTOM ≈ 4.38`, so end-to-end I6 (`α·gap > W−L = 3`) needs `α ≳ 0.69` — the old `0.6` (calibrated to the credit-level gap of 6) sits *below* it and inverts I6 end-to-end. `α = 0.75` clears it with margin (`credit(loss→elite) 1.67 > credit(win→weak) 1.42` on converged ratings) **and** is the argmax of the Stage-A rank-recovery sweep (`harness/tune.py`) over the scorable §7 scenarios; stays `<1` for the I9 contraction (`α(1−λ)=0.71`). *Falsifiable assumption held:* an α clears I6 end-to-end without breaking convergence or recovery. **Confirming test green:** `scenarios/test_s07_close_vs_tier.py` (end-to-end I6 at the shipped default) + `models/test_bespoke_tuning.py`. | Structural invariant safety (1) sets the floor; rank-recovery (2) picks within range. | Scenarios 7 (I6), 3, 4 (I10) + convergence sweep. *Falsified if* no α clears I6 end-to-end without breaking convergence or recovery — **not falsified.** |
| **Q2 `T`** | **`T = 1` (the 3/1/0 scale).** Tie sits ⅓ toward a win — well below midpoint = "tying is not winning, no big bump" (rule 2); most legible value. | Explainability (3); recovery expected insensitive (2). | Scenario 8 (I5) + sensitivity `T∈{0.5,1,1.5}`. *Falsified if* recovery moves materially with T → data decides. |
| **Q3 tier mod** | **Discrete (margin-bucket × tier) lookup table.** Stability comes from the §5 frozen recency-weighted window (that's what I13 is for), **not** from smoothing — smoothing by rating-gap would double-count `scheduleTerm`. Keep the two opponent channels orthogonal: `scheduleTerm`=strength-of-schedule, tier-table=how margin reads by tier. | Faithful to brief's 2-D surface + explainability (3); robustness via window (4). | Scenario 13 (no whipsaw once windowed) + **ablation**: each channel adds recovery, contributions not redundant (corr < ~0.7). *Falsified if* redundant → collapse to one channel. |
| **Q4 weak-team win** | **Real but *bounded* debit, in the `scheduleTerm` channel only.** Rule 6 ("negative signal") ⇒ genuine debit, not withheld credit. Safe: debit lives in schedule, never in `base`/`marginAdj`, and the floor (I7) is about margin + schedule-matched comparisons, so I1/I4/I5/I7 hold structurally. Cap magnitude both directions ("cap the benefit"). | Invariant safety (1) via channel isolation; brief intent. | Scenarios 3, 6 + constructed schedule-matched I7 case. *Falsified if* the debit ever flips a schedule-matched result order. |

**Cross-cutting:** Q1 and Q4 are the *same* channel (`scheduleTerm`) → co-tuned. Q3's tier table is a
*second* opponent-strength encoding → the Q3 ablation is the test that proves we don't pay for opponent
strength twice. These resolutions update the §9 strawman defaults; Stage A may overturn any of them.
