# TASK-18: Opponent-relative goal-profile residual (over/under-perform vs the opponent's goal baseline)

**State:** refined (fast-follow of TASK-17) · **Model:** **opus** — this is **model-core**
(`models/bespoke.py`): it adds a *third* opponent-strength-adjacent signal to per-game credit and must be
proven orthogonal to the existing channels. Sequential after TASK-17.
**Owns (files):** `models/bespoke.py` and its tests (`models/test_bespoke_*.py`); a **new confirming
scenario** `scenarios/test_s15_goal_profile.py` (+ a `build_s15_goal_profile` in `scenarios/builders.py`);
regenerates `reports/comparison.md` / real-data reports if they exist.
**Must NOT touch:** `generator/*`, `core/game.py`, `ingest/*`. Keep the observed-vs-derived wall and
determinism (I8/I9).
**Parallel-safe:** **NO — core-model, sequential.** Owns `models/bespoke.py`; never run beside TASK-17 or
any other bespoke.py task. Run `invariant-auditor` + `spec-keeper` after.
**Depends on:** **TASK-17 landed** (the surprise-centered credit recentering this refines).

---

## Why this exists (owner direction, deferred from TASK-17)

While resolving the closing-schedule floor cost (TASK-17), the owner asked for honor/penalty credit to be
shaped not just by *who* you played and the raw margin, but by **how you performed against that specific
opponent's own goal baseline**:

- **You scored more goals than they typically allow** → you beat their defense → extra credit.
- **They scored fewer goals than they typically score** → you suppressed their offense → extra credit.
- Conversely, conceding more than they usually score / scoring less than they usually allow → less credit.

This is a finer-grained "over/under-performance" signal than the closeness buckets TASK-17 ships. It was
**deliberately deferred** so it would not ride on the back of the floor rewrite — it needs its own
orthogonality proof and its own confirming scenario.

## The hard constraint — don't pay for opponent strength twice

The opponent's *typical goals-allowed* (GA) and *typical goals-for* (GF) are **measures of opponent
strength** (strong teams allow few, score many). TASK-17 already counts opponent strength via the
`own_rating + surprise` recentering (the surprise term scales with `opp − own`). Adding a raw "you scored a
lot" reward would **double-count** that — the exact failure mode CLAUDE.md forbids ("the two opponent-strength
channels must stay orthogonal; don't pay for opponent strength twice").

**Resolution (the design rule for this task):** the signal must be a **residual** — your goals measured
*relative to the opponent's own baseline*, centered so that getting the opponent's *expected* result against
them is **neutral** on this channel. A residual vs the level is orthogonal to the level by construction. The
surprise/recentering term remains the "who you played" channel; this term is "how you did vs what that
opponent normally yields, net of who they are."

## Observed-vs-derived wall — stays intact

The opponent's typical GF/GA are **aggregates computed from the Level-0 game log** (`goalsTeam` /
`goalsOpponent` per row), never a stored summary and never a rating fed back in. Computing them from the log
is explicitly sanctioned ("Always compute aggregates from the game log; never trust a stored summary"). The
term consumes Level-0 only.

---

## Read first

1. **`docs/work/tasks/TASK-17-closing-schedule-floor-cost.md`** — the surprise-centered credit this refines
   (the `own_rating + f(result, opp − own)` model and its convergence proof).
2. **`CLAUDE.md`** — orthogonal channels; don't double-count opponent strength; aggregates from the log;
   determinism is sacred.
3. **`docs/analysis/decision-memo.md`** §0.1/§0.2 — where the new term must slot in, and the contraction it
   must not break.
4. **`models/bespoke.py`** — `per_game_credit`, `base_and_margin`, the `_solve` aggregation; the TASK-17
   surprise term is what this composes with.

---

## Approach (TDD — failing confirming scenario first)

1. **Write S15** (`build_s15_goal_profile` + `scenarios/test_s15_goal_profile.py`): two teams with the **same
   record, same opponents, same raw margins**, differing only in goal-profile residual — Team OVER scores
   above / holds below each opponent's baseline; Team UNDER does the reverse. Planted truth makes OVER ≥
   UNDER. Assert the model ranks OVER ≥ UNDER. Watch it fail on the TASK-17 model (the residual isn't read).
2. **Design the residual term**: opponent GF/GA computed from the log; your game's goals centered on that
   baseline; bounded and centered so an *expected* score is neutral (orthogonality). Re-confirm the
   convergence proof still holds with the added term (it should be a bounded additive perturbation, but prove
   it). Preserve same-opponent I1 (the residual must not let a loss out-credit a win vs the *same* opponent).
3. **Implement to green on S15.**
4. **Full gate:** `pytest -q` (all I1–I13 + every §7 scenario incl. S14), regenerate `reports/comparison.md`
   (rank recovery must not regress), real-data confirmation re-run. `ruff check .` clean.
5. **`invariant-auditor`** + **`spec-keeper`** (especially: is the residual genuinely orthogonal to the
   surprise channel? any double-count of opponent strength? determinism?).

## Acceptance / Definition of done

- [ ] New scenario **S15** isolates the goal-profile residual (same record/opponents/margins) and fails on
      the TASK-17 model, passes on the new one (OVER ≥ UNDER), with planted truth.
- [ ] `models/bespoke.py` adds the **opponent-relative residual**, centered so an expected score is neutral;
      proven **orthogonal** to the surprise channel (no double-count); convergence re-confirmed; I1 preserved.
- [ ] All I1–I13 green; Stage-A rank recovery does not regress (before/after reported honestly).
- [ ] Real-data confirmation re-run; ranking artifact regenerated; determinism (byte-identical) intact.
- [ ] `invariant-auditor` + `spec-keeper` verdicts in the PR. `pytest -q` green; `ruff check .` clean.

## Out of scope

- **Anything TASK-17 owns** — this builds strictly on top of a landed TASK-17.
- **Walk-forward prediction / log-loss (B4)** — the eventual adjudicator; a separate task.
- **Changing the generator / world model**, **re-tuning unrelated params**, **touching `ingest/`/`analysis/`
  logic** — same boundaries as TASK-17.
