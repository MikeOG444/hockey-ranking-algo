# generator/

Synthetic **Dixon–Coles** world model + seeded scenario configs → emits `data/*.json`.

- Emits **Level-0 rows only** (`week,date,time,team,opponent,goalsTeam,goalsOpponent`) **plus a hidden
  ground-truth key** (true ratings/tiers/trajectories). No home/away term — there is no home team.
- Deliberately **not** any candidate model's own assumptions (avoids circular validation).
- Every scenario = config + fixed seed → reproducible. Schema: brief §8.

> Build after the data contract (Levels 0→1). See `docs/planning/PLAN.md` Phase 2.
