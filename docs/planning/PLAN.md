# Rating Model Spike — Execution Plan

**Goal of this spike:** identify the *correct* youth-hockey rating model — transparent, explainable,
deterministic, fair — that beats the MHR replica on synthetic ground truth and passes every invariant
in the brief (§4). Stage B (real-data prediction) is **deferred** to productionalization; this spike
proves *correctness against truth we control*.

**Decisions locked (2026-06-20):**
- **Stack:** Python (numpy/scipy/pandas, pytest). Port the winner to TS during productionalization.
- **Data:** Synthetic-only. Stage A is the whole game here. No scraping, no real logs this round.
- **Deliverable:** **Decision memo first** → then build only what's needed to decide.

The decision metric for this spike: *the bespoke model passes all §4 invariants on the §7 scenarios and
beats the MHR replica on Stage-A rank recovery, with readable per-game attribution.*

---

## Guiding method (from the brief, §0)

Design the tests first; let them define the model. Build order is bottom-up and test-anchored:
**data contract → generator → invariants-as-tests → models → run → review.** We do not tune the model
to look good; we tune it until the invariants hold and rank-recovery is strong against planted truth.

---

## Phase 0 — Decision Memo (no solver code yet)  ← *the gate for everything below*

A written technical design (`/docs/decision-memo.md`) that resolves the brief's open tensions into
concrete math, so we don't build the wrong thing. Until these are pinned, the solver is guesswork.

**0.1 The floor-vs-modulation resolution (the central tension, brief §1 note).**
Formalize per-game credit as an **additive decomposition** so modulation can never flip result order:

```
credit(game) = base(result)                      # the FLOOR: W=+W, T=+T, L=+L, with W>T>L
             + marginAdj(result, marginBucket)    # wins: bonus ≥0, diminishing; losses: penalty ≤0, 0 for close
             + scheduleTerm(opponentCurrentRating)# the only cross-opponent signal; drives I6/I10
```
- `base` is fixed per result → **I1 (ordering) is structurally guaranteed**, can't be overridden.
- `marginAdj` is bounded: wins add a diminishing, capped bonus (I2, I3); a *win's marginAdj never < 0*
  and a *loss's marginAdj never > 0* and is **0 for close (1–2)** losses (I4, I5).
- Tier modulation acts on `marginAdj` only (scales/translates the bonus/penalty), **never on `base`** → I7.
- The "close loss to elite is positive / close win over weak is negative" effect (I6) comes from
  `scheduleTerm`, not from `marginAdj` — it's a *different opponent*, so I1 (same-opponent) is untouched.
  **Memo must show I6 and I1 hold simultaneously with a worked numeric example.**

**0.2 The solve & convergence guarantee (I8, I9).**
Define the season rating as the fixed point of a **damped batch iteration**:
`r_i ← (1-λ)·mean_g[ w_g · credit_g(r_opponent) ] + λ·r̄` where `w_g` is recency × opponent-strength weight,
`λ` is regularization toward the mean (`r̄`). Argue uniqueness/convergence: with `λ>0` this is a
contraction (diagonally-dominant), giving a **unique fixed point independent of init/order** → I8, I9,
including sane low-confidence ordering on disconnected/bridge graphs (scenarios 1, 2). Memo states the
convergence tolerance and the deterministic tie-break (stable sort on id).

**0.3 Tier detection (brief §2).** Pick the default break algorithm and the model-selection rule for
the *number* of tiers. Candidates: largest-gap splits, Jenks natural breaks, 1-D k-means + BIC/elbow.
Default `tierCount:"auto"`, `tierMethod:"natural_gaps"`. Memo specifies how "auto" chooses k and why
(must reproduce the observed shape: isolated #1, tight top cluster, smooth field below ~30).

**0.4 The frozen-tier window math (brief §1.8, the determinism guarantee).**
Define precisely: recency-weighted read of an opponent's tier over ≤4 prior **finalized** weeks; the
decay shape; the per-team **consistency/stability measure**; how consistency modulates the confidence
(and thus how much credit a volatile opponent can confer → I13). Define cold-start (weeks 1–2 run
tier-agnostic; frozen window activates at ≥2–3 finalized weeks).

**0.5 Momentum/trend output (I11).** Define the trend signal — slope of the recency-weighted rating over
recent weeks — and how it's exposed alongside the point-in-time rating.

**0.6 The `rate(games)` interface contract.** Lock the common signature all models implement:
`rate(games, config) -> {ratings, tiers, perGameAttribution, trend}` so the harness can swap models.

**Exit criterion for Phase 0:** every invariant I1–I13 has a named mechanism in the memo, and the
6/7-vs-1/4/5 tension has a worked numeric counter-example proving it can't break. *Review with owner before coding.*

---

## Phase 1 — Data contract + scaffolding (Levels 0→1, model-agnostic)

Build and test the parts that need no model first (brief §5).
- Repo skeleton (§10 layout): `/generator /models /harness /scenarios /data /reports /docs`.
- **Level 0 schema** (`week,date,time,team,opponent,goalsTeam,goalsOpponent`) — no home/away, outcome inferred.
- **Level 1 aggregator** — fold game rows into `gamesPlayed,gf,ga,goalDiff,w,l,t,winPct`. *Always computed
  from games, never trusted from a summary.* Unit-tested in isolation.

## Phase 2 — Synthetic generator (brief §6, §8)

- Dixon–Coles world model (Poisson goals + low-score correction). **No home-ice term.** Deliberately
  *not* any candidate's own assumptions (avoids circularity).
- Inputs: `n_teams`, per-team true attack/defense (→ true rating), schedule (pairings + repeats),
  `week` index per game, fixed `seed`. Emits Level-0 rows **plus hidden ground-truth key**
  (true ratings, tiers, trajectories). Multi-week support for momentum/freeze scenarios.
- Reproducible: every scenario = config + seed. JSON per the §8 schema.

## Phase 3 — Invariant harness *as tests, written before models* (brief §4)

This is the heart — "let the tests define the model." Each invariant I1–I13 becomes an executable
assertion/pytest the candidates run against. Plus truth-scoring (Spearman/Kendall rank recovery,
centered RMSE/MAE, tier-boundary accuracy). Use **TDD**: write the failing invariant checks first.

## Phase 4 — Models behind the common interface (brief §3)

Minimum set to *decide*, in priority order:
1. **Bespoke model** (primary candidate, §3a strawman) — the Phase-0 design, implemented.
2. **MHR replica** (the incumbent to beat — "better" must be measured, not asserted).
3. **Ridge Massey** (transparent benchmark; cheap, sanity-checks rank recovery).

Defer **margin-Elo** and **Poisson/Dixon–Coles-as-rater** unless the decision is close or we want the
predictive-floor / calibration story. (We already *generate* from Dixon–Coles; adding it as a rater is
optional for Stage A.)

## Phase 5 — Scenario suite (brief §7)

Start with the three the brief calls out for end-to-end wiring, then fill the rest:
1. Disconnected clusters · 3. Schedule inflation ("Dallas") · 6. Win-but-should-drop.
Then: stale-opponent/float (4, I10), close-vs-tier (7, I6), tie handling (8, I5), momentum (11, I11),
blowout incentive (12, I3), tier instability/freeze-window sweep 1→4 (13, I13), plus
sparse-vs-dense (9), giant-killer (5), transitivity trap (10).

## Phase 6 — Run, review, decide

- Run all candidates × all scenarios → `/reports` comparison tables + invariant pass/fail matrix.
- **Gate:** bespoke must pass *every* §4 invariant. Record where benchmarks fail (the comparative story).
- Tune the §3a strawman params until invariants hold and rank-recovery is strong.
- **Decision output:** a short report naming the model + parameterization, with a per-game attribution
  example "a hockey parent can read," and the evidence (rank-recovery vs MHR replica, invariant matrix).

---

## Definition of done (this spike)

1. Decision memo resolves all tensions with worked examples (Phase 0). ✅ owner-reviewed.
2. Bespoke model passes **all** I1–I13 on the §7 scenarios.
3. Bespoke **beats the MHR replica** on Stage-A rank recovery against planted truth.
4. Per-game attribution + weekly-delta decomposition are human-readable.
5. Written recommendation: *this model, these params, this evidence* → hand off to productionalization.

## Explicitly out of scope (deferred to productionalization)
- Stage B real-data walk-forward backtest, log-loss/calibration, scraping last-season logs.
- TS port, hosting, the public demo UI.
- Margin-Elo / Poisson-as-rater unless the Stage-A decision is close.

---

## Risks / watch-items
- **Convergence on pathological graphs** (disconnected/bridge) — regularization `λ` must be proven, not assumed.
- **I6 vs I1 collision** — the single most likely place to get the math subtly wrong; gated in Phase 0.
- **Tier "auto" instability** — break detection can flicker; the frozen window (I13) is the guard, must be tested.
- **Circular validation** — never score a model with truth derived from its own assumptions; generator is Dixon–Coles for this reason.
