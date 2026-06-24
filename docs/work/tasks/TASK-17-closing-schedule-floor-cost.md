# TASK-17: Resolve the closing-schedule floor cost (opponent-aware recency + floor/schedule)

**State:** refined (blocked on a decision + 15/16) · **Model:** **opus** — this is **model-core**
(`models/bespoke.py`): it changes how per-game credit and/or recency weighting compose, and it directly
touches the I1/I6/I9/I11 machinery. Highest-stakes change since Stage A; opus, sequential, full invariant
gate.
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

## The user's direction + the known wrinkle

The owner's call: **make the recency-weighted rating opponent-aware** so a team that loses to elites late
isn't out-ranked by a team padding weak wins late. **Critical constraint proven in the analysis doc:**
re-weighting **alone cannot** reorder Woodbridge/Mid-Fairfield, because *every* MF late game (a loss, credit
~1.3–2.1) scores below *every* Woodbridge late game (a win, credit ~2.8–3.3) — when all of A's credits sit
below all of B's, no weighting reorders them. So the fix must **also** let an honorable loss out-credit a
cheap win (an opponent-strength term that can clear the floor for extreme opponents) **while preserving the
I9 contraction and same-opponent I1.** Opponent-aware recency + a floor-clearing schedule term, together.

## Decision gate (resolve BEFORE coding)

This is not a free win — it deliberately weakens the "a win is always worth more than a loss" simplicity that
the I1 floor gave us. Confirm with the owner which target:
- **(A) Ship the fix** — accept added complexity for real-world accuracy on closing-schedule disparity.
- **(B) Document-and-accept** — leave the model; record the cost as a known fairness tradeoff (then this task
  becomes a docs-only note, not a model change).
Default assumption pending confirmation: **(A)**, per the owner's stated direction. If (B), stop and
down-scope.

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
2. **Design the mechanism** (memo-style note in the PR, then code):
   - **Opponent-aware recency:** recency weight modulated by opponent strength so soft recent wins carry
     less than games vs strong opponents. Keep it orthogonal to the tier table (no double-count).
   - **Floor-clearing opponent term:** let the opponent-strength contribution grow (bounded, e.g. convex in
     `opp_rating` or a separate term) so a close loss to an elite can exceed a soft win — **re-derive the
     I9 contraction** for the new operator and prove it still converges (the single most important math
     check; mirror memo §0.2).
   - Preserve same-opponent I1 (the new term must be result-independent or floored so a win still ≥ a loss
     vs the *same* opponent).
3. **Implement to green on S14.**
4. **Run the full gate:** `pytest -q` (all I1–I13 + every §7 scenario), regenerate `reports/comparison.md`
   via `python -m harness.run` (rank recovery must **not regress** — report the before/after honestly), and
   run `python -m analysis.head_to_head` to confirm **Woodbridge now ranks below Mid-Fairfield Elite** on
   real data (the real confirmation). `ruff check .` clean.
5. **`invariant-auditor`** (adversarial I1–I13, especially I1/I6/I9/I11) and **`spec-keeper`** (orthogonal
   channels, no double-count, determinism, floor not breached) — include both verdicts in the PR.

---

## Acceptance / Definition of done

- [ ] Owner confirmed target (A) ship — or this is down-scoped to (B) docs-only.
- [ ] New scenario **S14** plants closing-schedule disparity; its test fails on the old model and passes on
      the new one (HONEST ≥ PADDER), with planted truth.
- [ ] `models/bespoke.py` change implements opponent-aware recency **and** a floor-clearing opponent term;
      the I9 contraction is **re-derived and proven** for the new operator (note in PR); same-opponent I1
      preserved.
- [ ] **All I1–I13 still green**; **Stage-A rank recovery does not regress** (`reports/comparison.md`
      regenerated; before/after reported honestly — if any scenario moves, explain why).
- [ ] Real-data confirmation: `analysis.head_to_head` shows **Woodbridge below Mid-Fairfield Elite**; the
      ranking artifact regenerated.
- [ ] `invariant-auditor` + `spec-keeper` verdicts in the PR; determinism (byte-identical artifacts) intact.
- [ ] `pytest -q` green; `ruff check .` clean.
- [ ] `docs/analysis/closing-schedule-floor-cost.md` updated from "open finding" to "resolved" (or "accepted"
      if (B)); BOARD row 17 flipped by the loop.

---

## Out of scope

- **Walk-forward prediction / log-loss (B4)** — the eventual adjudicator of whether this change predicts
  better; a separate task. This task fixes the *ranking inversion* against planted truth + head-to-head.
- **Changing the generator / world model** — the new scenario uses the existing trajectory + planting
  machinery.
- **Re-tuning unrelated params** (tier table, freeze window) — keep the change minimal and targeted; sweep
  only what the new mechanism introduces.
- **Touching `ingest/` or `analysis/` logic** — consume them; only regenerate their reports.
