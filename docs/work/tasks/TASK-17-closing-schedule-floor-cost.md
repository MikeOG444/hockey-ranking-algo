# TASK-17: Resolve the closing-schedule floor cost (opponent-aware recency + floor/schedule)

**State:** ready — **decision gate resolved 2026-06-24: ship (A), Approach 2 (surprise-centered credit).**
See "Design decision" below. · **Model:** **opus** — this is **model-core** (`models/bespoke.py`): it
**recenters** how per-game credit is computed (from absolute `base(result)` to `own_rating + surprise`) and
directly touches the I1/I6/I9/I11 machinery. Highest-stakes change since Stage A; opus, sequential, full
invariant gate.
**Owns (files):** `models/bespoke.py` and its tests (`models/test_bespoke_*.py`); a **new confirming
scenario** in `scenarios/` (builder + test) for the closing-schedule disparity pattern; regenerates
`reports/comparison.md` and `reports/real-h2h.md` / `reports/real-ranking.md` if those exist.
**Must NOT touch:** `generator/*` (consume `week_params`; don't change the world model), `core/game.py`,
`ingest/*`. Keep the observed-vs-derived wall and determinism.
**Parallel-safe:** **NO — core-model, sequential.** Owns `models/bespoke.py`. Never run beside any other
bespoke.py task (the 05→06→13 chain rule). Run `invariant-auditor` + `spec-keeper` after.
**Depends on:** the **finding** in [`docs/analysis/closing-schedule-floor-cost.md`](../../analysis/closing-schedule-floor-cost.md);
TASK-15 (real dataset, for the real-data confirmation) and ideally TASK-16 landed (so the ranking artifact
exists to regenerate). **Also depends on a human go/no-go** — see "Decision gate" below: this trades away
some invariant *simplicity* for accuracy, and that is an owner call.
**Branch from:** latest `main` after 16 merges — `/task 17` handles branch + PR.

> **Baseline:** `pytest -q` fully green; `data/real/mhr-2025-top50.json` present. Confirm, then write the
> failing confirming-scenario test **first**.

---

## The problem (one paragraph)

On real data, bespoke ranks **Woodbridge (#9)** above **Mid-Fairfield Elite (#14)** despite Mid-Fairfield
going **5-0 head-to-head** and playing a far tougher closing schedule (Jan–Mar avg opponent rating **+1.63**
vs Woodbridge's **+0.42**). Root cause (full write-up + arithmetic in the analysis doc): per-game credit is
`base + margin_adj + α·opp_rating` with **α < 1** required for I9 convergence, so the **max credit for any
loss (≈ α × top_rating ≈ 2.11) is below the 3.0 win floor** — a soft win always out-credits an elite loss,
and recency (I11) amplifies the disparity because both teams' lopsided games are late-season. This is the
synthetic **S05 giant-killer cost** (comparison §4 Cause 2) appearing on real data and compounded by recency.

## Decision gate — RESOLVED 2026-06-24

**Outcome: (A) ship, via Approach 2 (surprise-centered credit).** The owner reframed the fairness principle
in chat, which changed the *mechanism* (not just the justification). Both the reframe and the rejected
alternative are recorded below so a later reader understands **why the scope grew past the task's original
"add a bounded floor-clearing term" framing.**

## Design decision: reframe the floor, recenter credit on `own_rating + surprise`

**The reframe (owner's call).** The old fairness floor — *"a win must always count"* (a flat `base(win)=3.0`)
— is the wrong principle. Beating an opponent you beat 99.99% of the time demonstrates **no strength**, yet
the flat floor pays it full freight, which is exactly what inflates Woodbridge. The real fairness need a
parent has is narrower: **"a win is not a loss"** — you should never be *hurt for winning*. That fear is real
because MHR **caps goal differential**, so in a blowout mismatch you cannot "prove" dominance by margin; an
opponent-strength penalty could then net-*lower* a winner for a game they were scheduled into. The floor's
only job is to prevent that. So:

> **Credit tracks _surprise_.** An *expected* result moves you ~nothing; a *surprising* result moves you a
> lot. The floor is asymmetric on purpose: surprise can only ever *help* a winner, never hurt them — while
> ties and losses carry their full downside.

**Behavior the owner specified:**
- **Win** → never lowers your rating (at worst *neutral*); the gain *above* neutral scales with how strong
  the opponent was. Beat a cinch ≈ neutral; beat a peer-or-better → real gain.
- **Loss to a much *stronger* team** → neutral-ish, can *modestly raise* you (expected loss / near-upset).
- **Loss to a much *weaker* team** → absolutely lowers you (an upset against you).
- **Tie to a weaker team** → bad, should lower you.
- **Closeness buckets `1 | 2 | 3 | 4+`** scale the magnitude; **4+ is not a close game** (no honor credit).

**The mechanism (Approach 2 — recenter credit).** Per-game credit becomes `own_rating + f(result, opp − own)`
with the win-surprise term **clamped ≥ 0** (the win-only floor). This is the *only* design that delivers the
behavior above; see "Why not the minimal version" for the arithmetic proof that the task's original framing
cannot.

**Why not the minimal version (the task's original "floor-clearing term").** Keeping `base + margin + α·opp`
and merely *adding* a term (or a `max(own_rating, …)` floor) lifts an elite loss but **cannot make a cheap
win neutral** — a `max` only floors *up*, and an added term only raises the loss. The cheap win keeps banking
~3.3: Woodbridge beats a +0.42 team → `3.0 + 0.75·0.42 = 3.31`, while Mid-Fairfield loses to #1 → `0 +
0.75·2.81 = 2.11`, so **3.31 > 2.11 and the inversion never happens** — Woodbridge still inflates on the
*volume* of soft wins. To invert it that way you'd have to make a loss worth *more than a clean win* in
absolute terms (3.3+), which is the ugly form of weakening "a win beats a loss." Recentering on `own_rating`
makes the soft win ≈ Woodbridge's own rating (holds station, no inflation) and the elite loss ≈
Mid-Fairfield's own rating (slightly up) — **the inversion comes from *both* sides**, and same-opponent I1
(win > tie > loss vs the *same* team) is untouched.

**The convergence obligation (the central math check).** Recentering replaces today's affine `α<1`
contraction with an **Elo/Massey-style equilibrium**: the damped Jacobi update reduces to
`r ← r + λ·mean_g f(opp_g − r)`, whose fixed point is "mean surprise = 0." It converges when `f` has bounded
slope and `λ` is small enough — well-trodden, but a genuine **re-derivation** that the PR must prove (mirror
memo §0.2). Determinism (I8/I9) is preserved by a Jacobi sweep (every RHS evaluated at iterate *k*); the
win-clamp is `max(0, ·)` on the surprise term, not on `own_rating`, so it adds no order-dependence.

## Two things settled

1. **The confirming test is a deterministic synthetic scenario, not the real dataset.** Build a new §7-style
   scenario (`scenarios/builders.py` + a `scenarios/test_s14_closing_schedule.py`) that plants the pattern:
   Team **HONEST** loses close to several *elite* teams in the late weeks; Team **PADDER** beats several
   *weak* teams in the same late weeks; their early-season bodies of work are otherwise comparable. Planted
   truth makes HONEST ≥ PADDER. The model must rank HONEST ≥ PADDER. The **real** Woodbridge/Mid-Fairfield
   case is the *motivation* and a secondary confirmation, never the unit oracle (keeps tests deterministic
   and off real data).
2. **The full invariant suite is the gate — nothing may regress.** I1 (same-opponent floor) and I6 (close
   loss to elite > close win over weak, *same single pair*) must still hold; I9 must still converge to a
   unique fixed point (prove the contraction with whatever opponent term is added — α-equivalent must stay
   < 1 in operator norm); I11 momentum must still track current form; Stage-A rank recovery
   (`reports/comparison.md`) must **not regress** on the §7 scenarios. The new scenario S14 is *additive*.

---

## Read first

1. **`docs/analysis/closing-schedule-floor-cost.md`** — the finding, arithmetic, the α<1 ceiling, why
   re-weighting alone fails, the three options. This task implements option **2+3**.
2. **`CLAUDE.md`** — the fairness floor is structural (don't let margin/schedule touch `base`); the two
   opponent-strength channels (`scheduleTerm`, tier table) must stay orthogonal — **don't pay for opponent
   strength twice**; determinism is sacred (I8/I9). A floor-clearing opponent term must be designed *without*
   double-counting tier strength and *without* breaking same-opponent I1.
3. **`docs/analysis/decision-memo.md`** §0.1 (the additive `base + marginAdj + scheduleTerm` decomposition
   and why I1/I6 hold), §0.2 (the damped-iteration contraction → I9), §11 Q1 (α derivation, the <1
   constraint). Any new term must slot into this structure and re-derive the contraction.
4. **`models/bespoke.py`** — `per_game_credit` (`schedule_term = alpha·opp_rating`), `base_and_margin`,
   `rate_weekly` (the recency-weighted batch solve), the recency weight `w_g`. These are what change.
5. **`harness/test_harness.py`** (the I1–I13 MATRIX) and **`reports/comparison.md`** — the gate the change
   must survive.
6. **`scenarios/builders.py`** — the §7 builder idiom to mirror for S14.

---

## Approach (TDD — failing confirming scenario first)

1. **Write S14** (`scenarios/builders.py` `build_s14_closing_schedule` + `scenarios/test_s14_closing_schedule.py`)
   planting HONEST (late elite losses) vs PADDER (late soft wins), HONEST truly stronger. Assert the model
   ranks HONEST ≥ PADDER. **Watch it fail on today's model** (it will — that is the bug).
2. **Implement the surprise-centered credit** (memo-style note in the PR, then code) — per the resolved
   Design decision above:
   - **Recenter:** per-game credit = `own_rating + f(result, opp − own)`, with the **win-surprise clamped
     ≥ 0** (win-only floor — a win never lowers you). Beating a cinch ≈ neutral; ties/losses carry full
     downside (tie-to-weak and loss-to-weak lower you; loss-to-strong neutral-or-slightly-up).
   - **Closeness buckets `1 | 2 | 3 | 4+`** scale `f`'s magnitude; **4+ = no honor credit** on a loss.
   - **Re-derive convergence:** the affine `α<1` contraction is replaced by the Elo/Massey-style equilibrium
     `r ← r + λ·mean_g f(opp_g − r)` — **prove it converges** (bounded-slope `f`, small `λ`; the single most
     important math check; mirror memo §0.2). Determinism via a Jacobi sweep (all RHS at iterate *k*).
   - Preserve same-opponent **I1**: vs one opponent, `f` must order win > tie > loss, so a win still ≥ a
     loss vs the *same* team. The clamp is on the win-surprise, not on `own_rating`.
3. **Implement to green on S14.**
4. **Run the full gate:** `pytest -q` (all I1–I13 + every §7 scenario), regenerate `reports/comparison.md`
   via `python -m harness.run` (rank recovery must **not regress** — report the before/after honestly), and
   run `python -m analysis.head_to_head` to confirm **Woodbridge now ranks below Mid-Fairfield Elite** on
   real data (the real confirmation). `ruff check .` clean.
5. **`invariant-auditor`** (adversarial I1–I13, especially I1/I6/I9/I11) and **`spec-keeper`** (orthogonal
   channels, no double-count, determinism, floor not breached) — include both verdicts in the PR.

---

## Acceptance / Definition of done

- [x] Owner confirmed target **(A) ship, Approach 2 (surprise-centered credit)** — resolved 2026-06-24.
- [x] New scenario **S14** plants closing-schedule disparity; its test failed on the old model
      (HONEST 0.764 < PADDER 1.041) and passes on the new one (HONEST 0.352 ≥ PADDER 0.242), planted truth.
- [x] `models/bespoke.py` **recenters** per-game credit to `own_rating + surprise` with the **win-surprise
      floored at own rating** (the win-floor); the convergence is **re-derived and proven** — an
      unconditional `(1−λ)` contraction for any α ∈ [0,1) (memo §3.1); same-opponent I1 preserved. *(Closeness
      buckets stayed the existing margin machinery; the opponent-relative goal-profile residual is deferred
      to TASK-18.)*
- [x] **All I1–I13 still green.** **⚠ Stage-A rank recovery REGRESSED, by design and documented:** synthetic
      mean Spearman 0.8019 → 0.7031 (`reports/comparison.md` §4, full before/after + per-scenario). The
      regression concentrates in scenarios unrepresentative of real play (disconnected pods S01/S02, where the
      old floor only ranked by *accident*); the representative giant-killer S05 *improved* (0.357 → 0.500).
      **Owner accepted** this cost (ship + document) and pivoted evaluation to the real dataset (see TASK-19).
- [x] Real-data confirmation: Woodbridge **#9 → #18**, Mid-Fairfield (Elite) **#14 → #6**; `real-h2h.md`
      regenerated (deterministic).
- [~] `invariant-auditor` + `spec-keeper` verdicts — launched; included in the PR once they report.
      Determinism: `comparison.md` regenerates byte-identically (`test_report_is_deterministic` green).
- [x] `pytest -q` green (205 passed, 20 skipped, 2 xfailed); `ruff check .` clean.
- [x] `docs/analysis/closing-schedule-floor-cost.md` updated to **RESOLVED**; BOARD row 17 flipped to
      in-review by the loop.

---

## Out of scope

- **Opponent-relative goal-profile residual → fast-follow task.** The owner also wants honor credit shaped by
  *over/under-performance vs the opponent's own goal baseline*: scoring **above their typical goals-allowed**
  and **holding them below their typical goals-for** (aggregates computed from the Level-0 log — legitimate,
  on the right side of the observed-vs-derived wall). This is deliberately **deferred** so it doesn't ride on
  the floor rewrite: it adds a *third* opponent channel that needs its own **orthogonality proof** (don't pay
  for opponent strength twice — CLAUDE.md), its own determinism check, and its own confirming scenario. The
  Woodbridge inversion is achievable from **recenter + closeness** alone, so this task ships that first.
- **Walk-forward prediction / log-loss (B4)** — the eventual adjudicator of whether this change predicts
  better; a separate task. This task fixes the *ranking inversion* against planted truth + head-to-head.
- **Changing the generator / world model** — the new scenario uses the existing trajectory + planting
  machinery.
- **Re-tuning unrelated params** (tier table, freeze window) — keep the change targeted; sweep only what the
  new surprise mechanism introduces (`λ`, `f`'s slope/closeness scaling).
- **Touching `ingest/` or `analysis/` logic** — consume them; only regenerate their reports.
