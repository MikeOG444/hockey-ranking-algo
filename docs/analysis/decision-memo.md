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

### 1.1 `base` — the result floor (I1, I5)
```
base(W) = W,  base(T) = T,  base(L) = L,   with  W > T > L.   Strawman: 3 / 1 / 0.
```
Against the **same opponent**, holding margin fixed, `credit(W) ≥ credit(T) ≥ credit(L)` because the
`base` gap dominates and `marginAdj`/`scheduleTerm` are identical for the same opponent+margin. → **I1, I5.**

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
scheduleTerm = α · (R_j − r_i)              # you get credit for playing up, debit for playing down
             · resultWeight(result, B)       # close games vs strong teams count more as evidence
```
Because `scheduleTerm` is keyed to opponent `j`, it varies **across opponents** but is **identical for the
same opponent** — so it shifts cross-opponent comparisons (I6) **without ever affecting same-opponent
ordering** (I1). That orthogonality is the whole trick.

### 1.4 Why I1 and I6 cannot collide — *worked example*

I6 (brief §82): *a 1-goal loss to a top-tier team must rate better than a 1-goal win over a
bottom-of-field team.* I1: *vs the same opponent, win ≥ tie ≥ loss.* These feel contradictory; they aren't,
because they compare **different things**.

Let strawman `W=3, T=1, L=0`, `α=0.5`, close-game `resultWeight=1`, `marginAdj=0` for close games.
Ratings centered: elite team `R_elite=+4`, field team `R_field=−2`, our team `r_i=0`.

| Game | base | marginAdj | scheduleTerm = α·(R_j − r_i) | **credit** |
|---|---|---|---|---|
| 1-goal **loss to elite** | `L=0` | `0` (close) | `0.5·(4−0)= +2.0` | **+2.0** |
| 1-goal **win over field** | `W=3` | `0` (close) | `0.5·(−2−0)= −1.0` | **+2.0**… |

Tune so the loss-to-elite edges ahead (e.g. `α=0.6`: loss→+2.4, win→3−1.2=+1.8). **I6 satisfied.**

Now check **I1 is untouched**: against *that same elite team*, compare a win vs a loss. Both share the
**same** `scheduleTerm` (`0.6·(4−0)=+2.4`) and same close-`marginAdj` (0). Only `base` differs:
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

`perGameAttribution` returns, per game, the three terms `{base, marginAdj, scheduleTerm}` and `w_g`. By
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

## 9. Strawman defaults (starting point — Stage A will tune)

| Param | Default | Notes |
|---|---|---|
| `W / T / L` | `3 / 1 / 0` | result floor; ordering enforced here |
| `bonus[3/4/5+]` | `0.6 / 0.9 / 1.0` | diminishing: `Δ=0.6,0.3,0.1`; close=0 |
| `pen[3/4/5+]` | `0.5 / 0.8 / 1.0` | close=0; increasing |
| `α` (schedule) | `0.5–0.6` | tune so I6 example holds with margin to spare |
| `m(tier)/p(tier)` | per-tier-gap scalars | modulate adjustment only |
| `ρ` (game recency) | exp decay, ~½-life 3–4 wks | recent heavier |
| `λ` (regularization) | `0.05` | unique fixed point |
| `freezeWindowWeeks` | `4` | ≤4; swept in Stage B |
| `ρ_tier` | `= ρ` | independently tunable |

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
| **Q1 `α`** | **Derived, not guessed. Start `0.5`; sweep `0.3–0.8` in Stage A.** α is pinned by I6: `α > (W−L)/(elite−field gap) = 3/~6 ≈ 0.5`, and must stay `<1` for the contraction (I9). Floor at the I6 bound, cap below result-dominance. | Structural invariant safety (1) sets the floor; rank-recovery (2) picks within range. | Scenarios 7 (I6), 3, 4 (I10) + convergence sweep. *Falsified if* no α clears I6 without breaking convergence or recovery. |
| **Q2 `T`** | **`T = 1` (the 3/1/0 scale).** Tie sits ⅓ toward a win — well below midpoint = "tying is not winning, no big bump" (rule 2); most legible value. | Explainability (3); recovery expected insensitive (2). | Scenario 8 (I5) + sensitivity `T∈{0.5,1,1.5}`. *Falsified if* recovery moves materially with T → data decides. |
| **Q3 tier mod** | **Discrete (margin-bucket × tier) lookup table.** Stability comes from the §5 frozen recency-weighted window (that's what I13 is for), **not** from smoothing — smoothing by rating-gap would double-count `scheduleTerm`. Keep the two opponent channels orthogonal: `scheduleTerm`=strength-of-schedule, tier-table=how margin reads by tier. | Faithful to brief's 2-D surface + explainability (3); robustness via window (4). | Scenario 13 (no whipsaw once windowed) + **ablation**: each channel adds recovery, contributions not redundant (corr < ~0.7). *Falsified if* redundant → collapse to one channel. |
| **Q4 weak-team win** | **Real but *bounded* debit, in the `scheduleTerm` channel only.** Rule 6 ("negative signal") ⇒ genuine debit, not withheld credit. Safe: debit lives in schedule, never in `base`/`marginAdj`, and the floor (I7) is about margin + schedule-matched comparisons, so I1/I4/I5/I7 hold structurally. Cap magnitude both directions ("cap the benefit"). | Invariant safety (1) via channel isolation; brief intent. | Scenarios 3, 6 + constructed schedule-matched I7 case. *Falsified if* the debit ever flips a schedule-matched result order. |

**Cross-cutting:** Q1 and Q4 are the *same* channel (`scheduleTerm`) → co-tuned. Q3's tier table is a
*second* opponent-strength encoding → the Q3 ablation is the test that proves we don't pay for opponent
strength twice. These resolutions update the §9 strawman defaults; Stage A may overturn any of them.
