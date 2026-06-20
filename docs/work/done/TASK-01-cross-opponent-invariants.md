# TASK-01: cross-opponent invariants (I6, I7, I10) + attribution (I12)

**Status:** done
**Model:** opus — touches the fairness floor / solve; invariant-critical, design judgment required.
**Parallel-safe:** no — edits `models/bespoke.py` (single file) and these invariants interact. One chat, sequential.
**Depends on:** I8/I9 solve (done). **Branch from:** `f4c5895` (or main HEAD).

## Goal
Finish the bespoke model's cross-opponent behavior. The schedule term `alpha * R_j` (opponent's converged
rating) already provides the mechanism; this task proves it satisfies I6, I7, I10 and exposes per-game
attribution that reconciles to the rating (I12). After this, the only model work left is tiers (TASK-05)
and trend (TASK-06).

## Read first (context for a cold chat)
- `CLAUDE.md` (operating contract) + `docs/planning/operating-model.md` + this file.
- `docs/analysis/decision-memo.md` §1 (credit decomposition; note the two build-time corrections in §1.3),
  §1.4 (the worked I6-vs-I1 example), §7 (attribution), §10 (invariant→mechanism map).
- `docs/knowledge-bank/rating-model-test-brief.md` §4 (I6, I7, I10, I12 exact wording).
- Source: `models/bespoke.py` (the whole file — `per_game_credit`, `base_and_margin`, `rate`),
  `models/test_bespoke_credit.py`, `models/test_bespoke_rate.py`.

## Approach (TDD — write each test, watch it fail, then implement)

**I6 — close loss to elite > close win over weak.** Credit-level test on `per_game_credit`:
`credit(close LOSS, opp_rating=R_elite)` > `credit(close WIN, opp_rating=R_weak)` when `R_elite` is high and
`R_weak` low. Condition: `alpha*(R_elite − R_weak) > (W − L)`. With strawman `alpha=0.5, W−L=3` this needs the
rating gap > 6. **If it's marginal, raise `alpha` toward 0.6** (memo Q1 — α is derived, not fixed; 0.6 still
converges since `alpha*(1−lam)=0.57<1`). Pin the chosen α and note why. Also add an end-to-end version once
TASK-11 builds scenario 7 — out of scope here, just leave a note.

**I7 — underperformance never flips result.** Schedule-matched construction: two teams with the *same*
opponents, one wins every game by 1 (close), the other by 3. Their schedule terms are identical, so they
differ only by `marginAdj`. Assert: the by-3 team rates ≥ the by-1 team (gains more), BUT the by-1 team
still rates above every team it beat on results (never flips below a worse record). Build via the generator
or hand-built `GameRow`s.

**I10 — stale-opponent float (Dallas).** The solve is a single batch over all games, so an opponent's
schedule contribution uses its *converged* rating, never a stale early one. Construct: team X racks up early
wins vs weak teams but is truly weak (loses to strong teams later); a beneficiary Y that beat X must get
only `alpha * R_X(low)` credit. Assert Y is not inflated vs a control team that beat a genuinely strong team.

**I12 — attribution reconciles to the rating.** Populate `RateResult.per_game_attribution`: after
convergence, for each team build a list of `CreditBreakdown` (one per game, using final opponent ratings).
Expose enough that `rating_i == (1 − lam) * mean_g(breakdown.total) − center_offset` holds within 1e-9.
Store the centering offset (or the pre-center value) so the reconciliation is exact. Add the weekly-delta
result-vs-schedule split if cheap; otherwise note it for later. Assert the sum reconciles for every team.

## Acceptance / Definition of done
- [ ] New tests for I6, I7, I10, I12 pass; full `pytest` green; `ruff check .` clean.
- [ ] Chosen `alpha` documented in `BespokeParams` default + memo §9/§11 if changed.
- [ ] **Run `invariant-auditor`** on the bespoke model — it must confirm I1–I10 + I12 with evidence.
- [ ] **Run `spec-keeper`** — no floor breach / double-counting / nondeterminism.
- [ ] Commit in house style; move this file to `docs/work/done/`; update `README.md` status.

## Out of scope
Tiers / tier modulation (TASK-05), trend & recency (TASK-06), scenarios (TASK-11). Do not add a second
opponent-strength channel — keep `scheduleTerm` and (future) tier-table orthogonal (memo Q3).
