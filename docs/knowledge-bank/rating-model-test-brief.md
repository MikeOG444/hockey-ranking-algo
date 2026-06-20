# Rating Model — Design & Test Brief

**For:** Claude Code (build/execute). **From:** project owner + planning session.
**Goal:** Define and validate a youth-hockey rating/ranking model that is **transparent, explainable, deterministic, and fair** — and that fixes the specific failures we dislike in MyHockey Rankings (MHR). The model may end up conventional, a tuned variant, or genuinely novel; **the tests decide.**

**Method of work:** (1) lock the model's required *behavior* as testable invariants, (2) build a synthetic data generator with ground truth, (3) write edge-case scenarios + a metrics harness, (4) implement candidate models, (5) run the suite, (6) review and pick. Synthetic first (proves correctness against truth we control), then last-season real game logs (proves prediction). **Design the tests first; let them define the model.**

---

## 1. Design principles → hard requirements

These are non-negotiable properties. Each maps to invariants in §4.

- **Transparent / explainable.** For any team, we can list the exact games and the exact point contribution of each. No black box. A weekly rating change must decompose into named drivers (your results vs your schedule re-rating).
- **Deterministic.** Same input games → identical ratings every run. No random init, no order-dependence. This favors a **convergent batch solve** over online/stochastic methods (Elo/Glicko allowed only as benchmarks).
- **Fair**, defined concretely by the owner's rules below.

### Fairness rules (owner-specified)
1. **Result ordering is sacred.** Against the same opponent, a **win is never rated worse than a tie, and a tie never worse than a loss.** This is the cardinal rule MHR violates and we must not.
2. **Winning is winning; tying is not winning; losing is losing.** Ties get no "big bump." A tie sits strictly between win and loss credit.
3. **Margin matters in buckets, not linearly.** "Close" = **within 2 goals.** Buckets: **1–2 (close), 3, 4, 5+**, with **diminishing** credit at the top so blowouts don't run up the rating (cap the benefit, à la MHR's ±7 idea, but bucketed and explicit). More goals must **never reduce** a team's credit.
4. **Margin reward is floored at the result.** A win earns at minimum a win's credit; margin adds a *bonus on top*, it never replaces or undercuts the result. (This is how we "don't punish ugly wins" without "crippling the model.")
5. **Close losses avoid extra punishment — they do not earn a bonus.** A 1–2 goal loss takes the base loss credit but **not** the additional margin penalty that 3/4/5+ losses incur. A close loss is still a loss.
6. **Opponent strength matters, and margin × tier interact.** The *same* margin means different things by opponent tier:
   - A **close loss or tie to a top team is a positive signal** (you belong near that level).
   - A **close win over a weak team is a negative signal** (you underperformed expectation).
   - The credit function is therefore **two-dimensional: (margin bucket) × (opponent tier)**, not a single margin curve.
7. **Opponent strength floats (re-rates all season), but momentum is first-class.** Schedule credit uses opponents' *current* strength, not their stale early-season rating — this prevents the "beat a team that's now exposed and keep undue credit" problem (the Dallas case: a team stays inflated and its past opponents coast on it). **But** the model must also surface **trend/momentum** so rising/falling form is visible and isn't hidden the way MHR hides it. Recent games should carry more weight than season-opening games (recency weighting), and the output must expose a momentum/trend signal alongside the point-in-time rating.
8. **Tiers are frozen from recent finalized weeks, and self-consistent across the season.** Within a given week, the tiers used to credit that week's games are **frozen** from prior, already-finalized weeks — this breaks the chicken-and-egg loop (we never use this week's ratings to set this week's tiers) and **guarantees determinism**. Across the season, ratings and tiers still co-evolve and stay self-consistent, because each week is built from the converged output of the weeks before it. Specifics:
   - **Window:** a **recency-weighted window of up to 4 prior finalized weeks.** Recent weeks count more (decay); the frozen tier for an opponent is the recency-weighted read of where it has sat. This averages out single-week jitter without burying current form.
   - **Consistency matters across the window.** A team that has held the same tier across the window is treated with **higher confidence**; a team bouncing between tiers week to week is **lower confidence**, and its volatility is itself an exposed signal (it should not be allowed to whipsaw opponents' credit). Encode a per-team **tier-stability/consistency measure** over the window that modulates confidence (and feeds the momentum/trend output from principle 7).
   - **Boundaries still derived from gaps.** Each finalized week, tier boundaries come from natural gaps in that week's rating distribution (see §2), not hardcoded ranks. The *number* of tiers is an output. The window then freezes/recency-weights those finalized tier assignments.
   - **Cold-start.** The first ~2 weeks have no usable window. Run them **tier-agnostic** (or a single provisional pass), and begin applying the frozen window once ≥2–3 finalized weeks of history exist. State this explicitly; don't leave it implicit.
   - **Parameters to tune (Stage B):** window length (≤ 4), decay shape, and how strongly the consistency measure modulates confidence. Default the tier decay to **match the game-level recency weighting** (principle 7) for model coherence, but keep it independently tunable.

> **Tension to hold:** principles 6/7 (margin- and expectation-aware, floating) push toward methods that *can* drop you for underperformance; principles 1/4/5 forbid that from ever flipping result order. The resolution is the **floor**: expectation/tier/momentum modulate the *bonus*, never the *base result credit*. Tests must prove both hold simultaneously.

---

## 2. What the data says about tiers (already observed)

From the live USA 11U AAA top-100 (2025–26):
- **#1 is isolated** (97.28, a 1.65 gap to #2) — a tier of one.
- **#2–#11 cluster tightly** (95.63 → 93.59; largest internal step 0.72).
- **Minor seams at #12–#13** (0.66, 0.52 gaps).
- **#14–~#27 loose band; from ~#28 down it's a smooth continuum** (gaps ~0.03–0.15, no cliffs).

**Implication for the model:** real separation exists only near the top and dissolves into a gradient below ~30. **Do not hardcode 5/10/15/20/30/50/100.** Each **finalized week**, derive tiers via gap/break detection on that week's rating vector (e.g., largest-gap splits, Jenks natural breaks, or 1-D k-means with a model-selection criterion); expect ~3–5 meaningful bands at the top plus "the field." Those per-week tier assignments are then frozen and recency-weighted across the window (principle 8) to credit the current week's games. **Tier count and boundary method are a configurable parameter, not a constant** (`tierCount: "auto"` lets gap-detection choose the number; an integer pins it; `tierMethod` selects the break algorithm). Default to auto; allow an operator override.

---

## 3. Candidate models to implement and compare

Implement these behind a common interface `rate(games) -> {ratings, tiers, perGameAttribution, trend}` so the harness can swap them.

1. **MHR replica (incumbent / baseline to beat).** AGD (per-game goal diff capped ±7, averaged) + SCHED (mean opponent rating), solved iteratively as MHR does. This is the thing we're trying to beat; include it so "better" is measured, not asserted.
2. **Margin-Elo (cheap baseline).** Online, win/loss + margin-scaled K. Not deterministic-friendly; included only as a predictive floor.
3. **Ridge Massey (transparent benchmark).** Regularized least-squares on goal margins. Closest textbook analog to MHR done cleanly; strong transparency.
4. **Poisson / Dixon–Coles (accuracy benchmark + product features).** Attack/defense per team; predicts full scorelines → win probabilities and previews. Collapses to a single rating via attack−defense.
5. **The bespoke model (primary candidate).** A **transparent, deterministic, iteratively-solved, schedule-weighted, recency-weighted, bucketed-margin points model with a hard result-ordering floor** and a **(margin × tier)** credit surface. This is what principles §1 actually describe. Provide a **strawman parameterization** (§3a) as a starting point for the tests to attack and the backtest to tune.

### 3a. Strawman for the bespoke model (starting point, to be tuned — not final)
- **Base result credit (floor):** win = +W, tie = +T, loss = +L with `W > T > L` (e.g., 3 / 1 / 0 before adjustment). Ordering floor enforced here.
- **Margin bonus (wins only, diminishing, capped):** add on top of W — e.g., +0 for 1–2, +b3 for 3, +b4 for 4, +b5 for 5+, with `b3 > (b4−b3) > (b5−b4) ≥ 0` (diminishing). Never negative.
- **Loss margin penalty:** subtract from L — **0 for 1–2 (close)**, then increasing for 3/4/5+. Close loss = no extra penalty.
- **Opponent-tier modulation:** scale/translate the above by opponent tier so that close-vs-elite is rewarded and close-win-vs-weak is muted/flagged. Modulates the **bonus/penalty**, never the base result credit (preserves ordering).
- **Schedule + recency:** each game's contribution weighted by opponent *current* strength and by recency (recent games heavier). Season rating = weighted aggregation.
- **Per-week solve (tiers frozen):** within a week, tiers are **frozen** from the recency-weighted ≤4-week window (principle 8), so the within-week step is just ratings → tier-modulated credit → ratings given fixed tiers, run to convergence. No within-week ratings↔tiers loop. Add light regularization (prior toward mean) for a unique fixed point on sparse/disconnected graphs. Each finalized week then re-derives tiers (§2) to feed the next week's window.
- **Outputs:** point-in-time rating, derived tier, **trend/momentum** (e.g., slope of recency-weighted rating over recent weeks), and **per-game attribution** for explainability.

---

## 4. Invariants (must-pass unit tests)

These encode the principles as assertions. Every candidate is checked; the bespoke model must pass all. (Benchmarks may legitimately fail some — that's the point of measuring.)

- **I1 — Result ordering.** Holding opponent and margin fixed, `credit(win) ≥ credit(tie) ≥ credit(loss)`. No exceptions.
- **I2 — Win never punished by margin.** For wins, increasing margin never decreases credit. (Monotone non-decreasing in margin.)
- **I3 — Blowout cap.** Credit gain from margin 5+ over margin 3 is bounded/diminishing (no runaway for running up scores).
- **I4 — Close-loss floor.** A 1–2 goal loss is credited ≥ a 3+ goal loss to the same opponent, and never *above* a tie. (Avoids extra punishment without becoming a bonus.)
- **I5 — Tie placement.** A tie is strictly between win and loss credit vs the same opponent; ties produce no "big bump."
- **I6 — Tier × margin interaction.** **A 1-goal loss to a top-tier team rates better than a 1-goal win over a bottom-of-field team** (the owner's canonical example). Construct the exact case and assert.
- **I7 — Underperformance never flips result.** A strong team that wins all games by exactly 1 goal may *gain less* than expected but **must not drop below** a comparable team that won by larger margins, and must never rank below a team it would order above on results. (Floor holds under expectation modulation.)
- **I8 — Determinism.** Same games, run twice, byte-identical ratings/tiers. Shuffle input order → identical output.
- **I9 — Convergence & uniqueness.** With tiers frozen per week (principle 8), the within-week rating solve converges from different starting points to the same fixed point (within tolerance) on the test graphs. No multi-fixed-point / oscillation behavior.
- **I10 — Float correctness (stale-opponent).** If an opponent's true strength is lower than its early-season rating implied, credit for beating them reflects *current* strength, not the inflated past. (The Dallas/stale-beneficiary case.)
- **I11 — Momentum exposure.** A team on a rising true-strength trajectory shows a positive trend signal distinct from a flat-but-equal-rating team.
- **I12 — Explainability.** For any team, perGameAttribution sums to (within tolerance) the rating components; weekly delta decomposes into result-driven vs schedule-driven parts.
- **I13 — Tier stability / no whipsaw.** A frozen window of up to 4 finalized weeks damps single-week tier jitter: a one-week tier blip in an opponent must not swing the credit that opponent confers this week beyond a bounded amount, and a team's own consistency measure must read lower when its tier bounces week to week. Rankings must not churn from single-week noise.

---

## 5. Data contract — observed vs derived (applies to synthetic AND real data)

Strict separation between what we **observe** and what we **derive**. Nothing derived may ever be smuggled in as a model input. There is **no home/away and no venue** — these don't exist in our data.

**Level 0 — Observed (the only true inputs).** One row per game:
`team`, `opponent`, `date`, `time`, `goalsTeam`, `goalsOpponent`.
Outcome (W / L / T) is **inferred** from the two goal numbers — never stored as a primary field. There is no concept of which side was "home." `team` vs `opponent` is just the two participants.

**Level 1 — Team aggregates (pure arithmetic, no model needed).** Once a team has >1 game, fold the rows into: `gamesPlayed`, `gf`, `ga`, `goalDiff`, `w`, `l`, `t`, `winPct`. Deterministic counting on Level 0 only. (Lesson from the scrape: header `Record`/`Goals` fields were unreliable, but totals computed from the game log were exact — **always compute aggregates from games; never trust a stored summary.**)

**Level 2 — Model outputs (exist only after a rating run).** `rating`, `ranking`, `tier`. These cannot be inputs to the first pass — they are produced by the model, then feed forward as context.

**Level 3 — Performance vs strength (needs Level 2).** Once every team has a rating/ranking/tier, re-slice each team's games into `w/l/t` and `gf/ga` **vs each tier** and **vs ranked opponents / specific teams** (the "gauntlet" view, now from *our* ratings, not MHR's). The tier configuration (see §2) is active here.

Build order falls out of this: **Levels 0→1 are model-agnostic — build and test them first; Levels 2→3 only come online once a rating exists.** The synthetic generator emits only Level 0 rows (plus hidden ground truth); the harness derives everything above, which keeps the test honest.

---

## 6. Synthetic data generator (build after the data contract)

**World model: Poisson/Dixon–Coles** (most hockey-like; forces margin methods to recover truth from data not built in their image). Avoid simulating from any candidate's own assumptions — that would be circular.

**Generator spec:**
- Inputs: `n_teams`, per-team **true** attack & defense (→ implied true rating = attack − defense), a **schedule** (pairings + repeat counts), a **week index** per game (drives recency/freeze window/backtest), and a **fixed seed**.
- Each game: draw both teams' goals from Poisson with their attack/defense (+ optional Dixon–Coles low-score correction). **No home-ice term — there is no home team.** Emit a Level-0 row: `{week, date, team, opponent, goalsTeam, goalsOpponent}`.
- Output: a Level-0 results table identical in shape to scraped data **plus a hidden ground-truth key** (true ratings, true tiers, true trajectories). Levels 1–3 are computed by the harness, never emitted as input.
- **Seeded and reproducible.** Every scenario is a fixed seed + config.

**Scoring against truth:**
- **Rank recovery:** Spearman/Kendall between recovered and true ratings.
- **Rating error:** RMSE/MAE on rating values (after centering, since ratings are relative).
- **Tier accuracy:** do recovered tier boundaries match the planted ones (under the active tier config).
- **Calibration:** if the model emits win probabilities, do stated 70% chances win ~70% (reliability curve, Brier/log-loss).
- **Invariant checks:** §4 assertions pass/fail.

---

## 7. Edge-case scenarios (the test set)

Each is a seeded generator config + expected behavior. These are where models break — mostly **schedule-graph structure**, plus the owner's fairness cases.

1. **Disconnected clusters.** Two regional pods that never cross. Expect: methods that can't place clusters relative to each other are flagged; regularization yields a sane (low-confidence) ordering. Tier detection must not invent false separation.
2. **Single bridge game.** One game links two clusters. Measure how confidently/recklessly each method rates across one thread of evidence.
3. **Schedule inflation (the "Dallas" case).** A strong-recorded team that played only weak opponents vs. an equal-record team that played a tough slate. **Assert the padded team rates below** the gauntlet team. Ties to I6/I10.
4. **Stale opponent / float test.** A team beats an opponent that was strong early but is truly weak; that opponent's rating must re-rate down and the beneficiary must not coast. Assert I10.
5. **Giant-killer / noise.** A team whose results contradict its true strength (lucky run). Check robustness — model shouldn't overreact; uncertainty/trend should reflect it.
6. **Win-but-should-drop.** A strong team wins everything by exactly 1 goal. Assert I7 (gains less, never flips order, never ranks below larger-margin equals).
7. **Close-vs-tier.** Construct I6 directly: same team has (a) a 1-goal loss to a top-tier side and (b) a 1-goal win over a field team; assert the loss-to-elite contributes more.
8. **Tie handling.** Teams differing only in ties vs wins/losses; assert I5 ordering and "no big bump."
9. **Sparse early vs dense late.** Same true strengths at ~5 games/team vs ~40; measure convergence speed and stability of ranking week to week.
10. **Transitivity trap (A>B>C>A).** Rock-paper-scissors loop; check each method resolves it sensibly and deterministically.
11. **Momentum.** Two teams, equal season-average true rating, one rising / one falling within the season; assert I11 (trend distinguishes them) and that recency weighting reflects current form.
12. **Blowout incentive.** A team that runs up scores (many 8–0s) vs one with the same wins by 2–3; assert I3 (no runaway advantage for blowouts).
13. **Tier instability / freeze window.** A multi-week simulation where one opponent's tier blips up for a single week, then returns. Assert I13: with the ≤4-week recency-weighted frozen window, the credit that opponent confers this week barely moves, the team's consistency measure reads low, and rankings don't churn. Run the same scenario across window lengths 1–4 to show the single-week freeze whipsaws and the windowed freeze does not. (Requires the time/`week` index on games.)

(Owner note: do **not** over-index on cold-start/mid-season-entry teams — top-50 teams reach ~10 games within the first month, top-20 reach ~5 by week 3. A light sparse-data scenario (#9) covers it; no special new-team machinery needed.)

---

## 8. Test data JSON schema

Generator emits, per scenario:

```json
{
  "scenario": "schedule_inflation",
  "seed": 42,
  "worldModel": "dixon_coles",
  "config": { "tierCount": "auto", "tierMethod": "natural_gaps", "freezeWindowWeeks": 4 },
  "groundTruth": {
    "teams": [{ "id": "T01", "trueAttack": 3.1, "trueDefense": 1.2, "trueRating": 1.9, "trueTier": 1, "trajectory": "flat" }]
  },
  "games": [
    { "week": 1, "date": "2025-10-03", "time": "10:45", "team": "T01", "opponent": "T07", "goalsTeam": 5, "goalsOpponent": 2 }
  ],
  "expect": {
    "invariants": ["I1","I3","I6","I10"],
    "assertions": [
      { "type": "ratesBelow", "a": "T_padded", "b": "T_gauntlet" }
    ]
  }
}
```

**`games` is Level-0 only** (§5): `week`, `date`, `time`, `team`, `opponent`, `goalsTeam`, `goalsOpponent`. **No `home`/`away`** — the two teams are peers; outcome is inferred from the goals. The `week` index is **required** — it drives recency weighting, the frozen-tier window (principle 8), and the walk-forward backtest. `config` carries the tunable knobs, notably **`tierCount`** (`"auto"` = let gap-detection decide, or pin an integer) and **`tierMethod`** — tiers are a configurable parameter, not a constant (§2). For multi-week scenarios (e.g., 11 momentum, 13 tier instability), `groundTruth.teams[].trajectory` describes how true strength moves over weeks (e.g., `"rising"`, `"falling"`, `"blip@w3"`).

Real-data backtest reuses `games` (dated, no `groundTruth`) and scores by prediction instead.

---

## 9. Two-stage validation plan

**Stage A — Synthetic (correctness).** Run all candidates on §7 scenarios. Gate the bespoke model on passing every §4 invariant; record where benchmarks fail (that's the comparative story). Tune the strawman (§3a) parameters here until invariants hold and rank-recovery is strong.

**Stage B — Real backtest (prediction).** Pull **last season's full, dated game logs** (broad — not just top-20; you need the connected graph). Walk forward week by week: at each week, each model rates on games-to-date and predicts the upcoming week; score with **log-loss + calibration** on win/loss and **RMSE on scores** (for Poisson). Include the MHR replica as incumbent. The model that predicts next week best — among those that pass Stage A invariants — wins, and ships next season having earned it.

**Tier-freeze tuning (within Stage B).** Sweep the frozen-tier **window length (1 → 4 weeks)**, the **decay shape**, and the **consistency-modulation strength**. Score each setting on two axes that trade off: **prediction** (log-loss/calibration of next week) and **churn** (week-to-week rank volatility — how much the ranking moves from noise vs. signal). The goal is the shortest window that predicts well *without* thrashing; expect the sweet spot at 2–4 weeks with recency decay. Confirm the single-week setting visibly whipsaws and the windowed setting does not (mirrors scenario 13).

> Partial-schedule reality (we don't get the full season schedule, only some upcoming games each week) affects **forecasting standings**, not computing the rating. Forecast with whatever upcoming games exist that week and refresh weekly.

---

## 10. Suggested repo layout / workflow for Claude Code

```
/generator      # synthetic world model + scenario configs (seeded) -> /data/*.json
/models         # mhr_replica, ridge_massey, dixon_coles, margin_elo, bespoke  (common interface)
/harness        # invariant checks, truth-scoring, calibration, walk-forward backtest
/scenarios      # §7 configs + expected assertions
/data           # generated test JSON (synthetic) + last-season logs (stage B)
/reports        # per-run results, comparison tables, reliability plots
```

Build order: generator + schema → 2–3 scenarios end to end (disconnected clusters, schedule inflation, win-but-should-drop) → MHR replica + ridge Massey + bespoke → invariant harness → full scenario suite → review → (Stage B) real backtest.

**Definition of done for v1:** the bespoke model passes all §4 invariants on §7 scenarios, beats the MHR replica on Stage A rank-recovery, and is competitive-or-better on Stage B prediction — with per-game attribution and a weekly-delta decomposition that a hockey parent can read.

---

*Context: USA 11U AAA, 2025–26, MyHockey Rankings. Sample / non-commercial. The aim is a rating that is transparent, explainable, deterministic, and fair by the rules in §1 — fixing MHR's ugly-win punishment, stale-schedule effects, and over-rewarded ties, without crippling the margin and schedule signal.*
