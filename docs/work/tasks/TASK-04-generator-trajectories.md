# TASK-04: multi-week trajectories in the generator

**State:** ready · **Model:** sonnet — generator feature from a clear spec.
**Owns (files):** `generator/simulate.py`, `generator/world.py`, `generator/test_*.py`.
**Parallel-safe:** yes (disjoint from TASK-03). **Depends on:** generator core (done, on `main`).
**Branch from:** latest `main` — the `/task 04` loop handles branch + PR.

## Goal
Let a team's true strength change over weeks so momentum/instability scenarios are possible. Required by
scenario 11 (momentum) and scenario 13 (tier blip) — see brief §7. Today `TeamParams.trajectory` exists but
is ignored; this makes it drive week-indexed attack/defense.

## Read first
- `CLAUDE.md`, `docs/planning/operating-model.md`, this file.
- `docs/knowledge-bank/rating-model-test-brief.md` §6 (generator spec), §8 (`trajectory` field: `"rising"`,
  `"falling"`, `"blip@w3"`, `"flat"`), §7 scenarios 11 & 13.
- Source: `generator/simulate.py` (`TeamParams`, `simulate`), `generator/world.py`, `generator/test_simulate.py`.

## Approach (TDD)
Add a deterministic mapping from `(TeamParams, week) -> (attack, defense)` driven by `trajectory`:
- `flat` (default) — unchanged.
- `rising` / `falling` — monotone drift in rating across weeks (move attack and/or defense by a per-week step).
- `blip@wN` — a one-week bump at week N, back to baseline after (for the freeze-window scenario 13).
`simulate` evaluates each matchup with the teams' week-N params. Keep it seeded and fully reproducible.
- Test: a `rising` team's expected goals (and realized goal diff over repeats) are higher in later weeks than early.
- Test: `blip@w3` perturbs only week 3; weeks 2 and 4 match baseline.
- Test: `flat` is byte-identical to current behavior (no regression); same seed reproducible.
- Keep the hidden ground truth honest: expose the trajectory (and optionally per-week true ratings) so the
  harness can score momentum recovery (I11) later.

## Acceptance / Definition of done
- [ ] New trajectory tests pass; existing generator tests still green; `ruff check .` clean.
- [ ] `flat` path unchanged (regression-safe). Commit in house style; flip the board row to `in-review`; open a PR and stop for approval.

## Out of scope
No model/harness changes. Don't build scenarios here (TASK-11) — just the generator capability they need.
