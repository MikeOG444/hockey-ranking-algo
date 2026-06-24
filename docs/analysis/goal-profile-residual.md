# Goal-profile residual — design + finding (TASK-18)

**Status:** **SHELVED 2026-06-24 (owner).** Prototyped, measured against the real-data gauntlet, and
**not shipped** — it could not be shown to help the real gate. Kept as a documented negative result;
revisit when walk-forward prediction (Stage-B B4) gives a real accuracy adjudicator. The confirming
scenario S15 is retained as a strict `xfail` (`scenarios/test_s15_goal_profile.py`) pinning exactly
what the shipped model deliberately does **not** do.

## The owner's intent

MHR rewards a strong team beating a weak one by demanding a large goal margin, then *caps* the
differential (a 90-rated team "should" beat an 80 by 10 but only 7 counts). The owner's reframe:
**the answer is not a larger goal-diff cap — it's how the team actually performed against *this*
opponent's own baseline.** Concretely:

- A strong team playing a weak one is *expected* to score a lot and concede little. Did they actually
  exceed what that weak team normally allows, and hold them below what they normally score?
- On the losing side: losing **1-0 to a team 10 points better** is a *strong* loss (already handled by
  the TASK-17 surprise channel — an expected loss barely moves you). But **scoring 3 more than a team
  typically allows yet still losing by 2** is *also* good — and nothing in the model reads that.

## The design that was prototyped

Per game, from team *i* vs opponent *j*, using *j*'s full-season mean goals-for / goals-allowed
(`GF_j` / `GA_j`, an observed aggregate from the Level-0 log — never a rating fed back in):

```
off = clamp(GF_i − GA_j, −C, +C)     # you vs what they usually ALLOW (offense)
def = clamp(GF_j − GA_i, −C, +C)     # them vs what they usually SCORE (defense)
goal_profile = β · (off + def)        # a fifth named driver of per-game credit
```

This was carefully shaped to be safe **by construction** (and that part held up — see below):

- **The trap, avoided.** The naive *symmetric* residual `(GF_i − GA_j) + (GF_j − GA_i)` collapses
  algebraically to `your_margin + opponent's_typical_goal_differential` — which adds nothing against a
  fixed opponent **and double-counts opponent strength** (the second term ∝ opponent strength), the
  exact failure CLAUDE.md forbids. Per-channel **clamping** breaks that linear collapse; **centering**
  on the opponent's own baseline (an expected score → 0) keeps it orthogonal to the surprise channel.
- **Convergence (I9) untouched.** `GF_j` / `GA_j` are rating-independent, so the term is a per-game
  *constant* — it never re-rates, and the `(1−λ)` contraction of memo §3.1 is unchanged.
- **Same-opponent I1 reinforced.** Vs the same opponent, a win has more goals-for and fewer
  goals-against than a loss → both clamped channels are weakly larger → the term can only widen
  win-over-loss, never invert it, for any β ≥ 0.

The full invariant suite (I1–I13) stayed green at β=0.05, C=2.0, and the term *reinforced* I6 (a close
loss to an elite over-performs their defensive baseline; a close win over a weak team under-performs).

## Why it was shelved — the real-data evidence

The owner's evaluation gate is the **real MHR dataset**, scored by agreement with the head-to-head
gauntlet (`analysis.head_to_head`, Spearman ρ vs the intra-top-50 points% ranking). A β-sweep against
that gate (clamp C, weight β; baseline β=0 is the shipped TASK-17 model):

| C | β | real-gauntlet ρ | beats MHR replica (0.8296)? | S15 (synthetic fairness) |
|---|---|---|---|---|
| — | 0.00 (no residual) | **0.8351** | ✅ yes | ✗ fails (OVER == UNDER) |
| 1.0 | 0.01 | 0.8352 | ✅ yes | ✅ passes |
| 1.0 | 0.02 | 0.8305 | ✅ yes | ✅ passes |
| 1.0 | 0.03 | 0.8260 | ❌ no | ✅ passes |
| 2.0 | 0.01 | 0.8315 | ✅ yes | ✅ passes |
| 2.0 | 0.02 | 0.8198 | ❌ no | ✅ passes |
| 2.0 | 0.05 | 0.8031 | ❌ no | ✅ passes |

**The verdict.** Real-gauntlet agreement falls **monotonically** as the residual strengthens. There is
**no β where the residual improves the real gate** — at best (β≈0.01) it is a rounding-level non-effect
while still flipping the synthetic S15 fairness scenario green; at the magnitude where it is a
meaningful signal (β=0.05) it drops bespoke *below* the MHR replica on the gate the owner chose.

**How to read that honestly.** The gauntlet is a points%-based *proxy*, not ground truth — it literally
cannot see the fairness this signal encodes (a points% ranking just counts a 1-0 loss to an elite as a
loss). So some disagreement is expected and arguably *correct*. But the proxy is the only real yardstick
available, and it cannot *prove* the residual is right. The residual is a **fairness refinement, not an
accuracy win**, and the real gate confirms it is not free. With no positive evidence on the gate that
now governs the project, the owner shelved it rather than ship added model complexity on faith.

## What is retained

- **This note** — the design, the avoided trap, and the negative-result evidence.
- **`scenarios/builders.py::build_s15_goal_profile`** + **`scenarios/test_s15_goal_profile.py`** — the
  scenario that isolates the goal-profile signal, kept as a strict `xfail`: it documents precisely what
  the shipped model does not do, and will flag (XPASS) if a residual is ever reintroduced.

## What was removed

- The `goal_profile` driver, params (`goal_profile_weight`, `goal_profile_clamp`), and the
  `opponent_goal_baselines` / `goal_profile_residual` helpers in `models/bespoke.py` — reverted, so the
  model is byte-identical to the post-TASK-17 baseline (`reports/comparison.md` /
  `reports/real-h2h.md` regenerate unchanged).

## If revisited (Stage-B B4)

Walk-forward prediction with a real accuracy metric (log-loss / Brier on held-out games) would be a
direct adjudicator the gauntlet proxy is not. If the residual demonstrably lowers held-out prediction
error there, it earns its place; the safe-by-construction design above is ready to re-instate.
