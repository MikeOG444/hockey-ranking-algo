# The closing-schedule floor cost (real-data finding)

**Status: RESOLVED (2026-06-24, TASK-17)** — fixed by **surprise-centered credit** (option 2+3, strong
form). Per-game credit was recentered from the `base = 3/1/0` floor to `own_rating + surprise`: an
*expected* win (beating a much weaker team) is ~neutral (the win is floored at your own rating) and a
close loss to an elite earns a small positive surprise. The owner reframed the fairness principle from
*"a win must always count"* to *"a win is not a loss"* to allow it.

**Real-data confirmation:** Woodbridge fell **#9 → #18**, Mid-Fairfield (Elite) rose **#14 → #6** — the
5-0 head-to-head winner now ranks above the team it swept; schedule-padded Dallas Stars Elite (7-9-1)
dropped out of the top 20 (`reports/real-h2h.md`). Synthetic confirming scenario: **S14**
(`scenarios/test_s14_closing_schedule.py`). **Cost (reported honestly):** synthetic rank recovery
regressed 0.8019 → 0.7031, concentrated in scenarios unrepresentative of real play — which motivated the
methodology pivot to evaluating on the **real MHR dataset** going forward (`reports/comparison.md` §4).
All I1–I13 still hold; the solve is now an unconditional `(1−λ)` contraction.

The original open-finding analysis is preserved below as the motivating write-up.

---

**Original status:** open finding from Stage-B B2 analysis (real MHR 2025-26 top-50). Motivated the
model-core task (TASK-17). The most consequential weakness the real-data run surfaced.

## The symptom

On the full-season real run, bespoke ranks **Woodbridge Wolfpack #9** above **Mid-Fairfield (Elite) #14** —
even though Mid-Fairfield **beat Woodbridge in all five head-to-head meetings** (2-1, 11-2, 6-3, 2-1, 7-2;
outscored them 28-9) and is ahead on the pure head-to-head gauntlet (MF #6 vs Woodbridge #8). Bespoke
disagrees with both the direct head-to-head *and* the record.

## The cause — a closing-schedule disparity the floor can't see

The two teams' January–March schedules were wildly different in strength:

| Jan–Mar | Games | Avg opponent bespoke rating | What they did |
|---|---|---|---|
| **Mid-Fairfield (Elite)** | 23 | **+1.627** | A murderers' row — Little Caesars, Florida Alliance, #1 Middlesex, Chicago Fury, Boston Advantage, Boston Jr Eagles. Went 16-14-3. |
| **Woodbridge** | 21 | **+0.418** | The bottom of the pool — NYC HC, NJ Rockets, Long Island, Lehigh Valley, Springfield + 3 unranked. Went 22-6-1. |

Mid-Fairfield's late "fade" was honorable losses to elite teams; Woodbridge's late "surge" was beating weak
ones. Recency weighting (I11) concentrates weight on exactly these late games, so the disparity drives the
final rating.

## Why bespoke can't see it — the structural ceiling

Per-game credit is `base(result) + margin_adj + schedule_term`, with `schedule_term = α · opp_rating` and
**α = 0.75**. Computed credits for representative late games:

| Game | base | margin | schedule | **credit** |
|---|---|---|---|---|
| Woodbridge **beats** a +0.42 team (3-1) | 3.00 | 0 | +0.32 | **3.31** |
| Woodbridge **beats** a −0.30 team (4-2) | 3.00 | 0 | −0.22 | **2.77** |
| Mid-Fairfield **loses** to Little Caesars +2.28 (1-2) | 0 | 0 | +1.71 | **1.71** |
| Mid-Fairfield **loses** to #1 Middlesex +2.81 (0-1) | 0 | 0 | +2.11 | **2.11** |
| Mid-Fairfield **loses** to Florida Alliance +1.68 (2-3) | 0 | 0 | +1.26 | **1.26** |

**Losing to the #1 team in the country (2.11) earns less than beating a near-zero team (2.77–3.31).** And
this is not removable by tuning α, because:

> **α must stay below 1** — it is the contraction factor that guarantees the solver converges to a unique
> fixed point (I9). The strongest team is rated ≈ +2.81, so the **maximum credit any loss can earn is
> ≈ 0.75 × 2.81 = 2.11 < 3.0**, the win floor. Therefore, with α < 1, **beating any positive-rated team
> always out-credits losing to anyone — including the #1 team.**

The fairness floor — "a win is always worth more than a loss" (the I1 principle parents asked for) — has a
hard structural cost: it cannot recognise that Woodbridge's wins were cheap and Mid-Fairfield's losses were
earned. This is the **same tradeoff as the synthetic S05 giant-killer** (`reports/comparison.md` §4 Cause
2), now with a real example and **compounded by recency** (which amplifies the soft closing schedule).

## Why re-weighting alone is not enough (important for the fix)

The natural fix is "make recency opponent-aware" — down-weight recent wins over weak teams, up-weight games
vs strong teams. **But re-weighting cannot, by itself, reorder these two teams.** Every one of
Mid-Fairfield's late games is a loss (credit ≈ 1.3–2.1); every one of Woodbridge's late games is a win
(credit ≈ 2.8–3.3). When *all* of A's per-game credits sit below *all* of B's, no choice of weights over
those games changes which has the higher weighted mean. To un-invert them you must also **raise the credit
of an elite loss above the floor of a soft win** — i.e. let `schedule_term` (or some opponent-strength
term) *clear the win floor* for extreme opponents. That collides with the α < 1 convergence guarantee, so it
needs the full invariant gate, not a knob twist.

**Conclusion: the fix is likely opponent-aware recency _and_ a floor/schedule change that lets an honorable
loss out-credit a cheap win — and a confirming scenario must prove it does, without breaking I1/I6/I9/I11.**

## Options (for TASK-17 to resolve via TDD)

1. **Document-and-accept** — declare it the known fairness-floor cost and leave the model as-is. Cheapest;
   keeps every invariant; loses real accuracy on closing-schedule disparity. (Current default.)
2. **Opponent-aware recency** — make the recency weight depend on opponent strength so soft late wins are
   discounted. Necessary but, per above, **not sufficient** on its own for this case.
3. **Let schedule clear the floor for extreme opponents** — allow `schedule_term` (or a new bounded
   opponent term) to grow non-linearly so a loss to a top team can out-credit a soft win, while preserving
   the I9 contraction and same-opponent I1. The hard, correct fix — gated by the full invariant suite.

The honest adjudicator remains the **walk-forward backtest (B4)**: does Woodbridge's soft surge actually
*predict* future wins? If not, this is confirmed as a defect and option 2+3 are warranted; if it does, the
recency feature is earning its keep and option 1 stands.

## Provenance

All numbers from `data/real/mhr-2025-top50.json` (TASK-15) via `python -m analysis.head_to_head`'s rater
run; per-game credits from `models.bespoke.per_game_credit` at shipped defaults (α = 0.75, ρ = ρ_tier = 0.2).
