# TASK-16: Head-to-head agreement + giant-killer case studies (real data)

**State:** refined (blocked on 15) · **Model:** sonnet — analysis + reporting that *consumes* the settled
raters and the real dataset; **no model-core change, no new model math**. It runs bespoke + the MHR replica
full-season on the cleaned real log and compares orderings to the head-to-head record. Clear spec, strong
oracle (the validated league-intel numbers) → sonnet.
**Owns (files):** a **new** `analysis/` package — `analysis/head_to_head.py` + `analysis/test_head_to_head.py`;
the generated report `reports/real-h2h.md`. Consumes `data/real/mhr-2025-top50.json` (TASK-15's output) and
the raters **read-only**.
**Must NOT touch:** `models/*`, `generator/*`, `harness/*`, `scenarios/*`, `ingest/*`, `core/*`,
`reports/comparison.md`. Purely additive analysis.
**Parallel-safe:** **yes, once 15 is merged** — its Owns set (new `analysis/` package + new report) is
disjoint from everything. It is **blocked only by the data dependency** on TASK-15, not by any file overlap.
**Depends on:** **TASK-15** (needs `data/real/mhr-2025-top50.json`). Flip this row `ready` the moment 15 is
`done`.
**Branch from:** latest `main` after 15 merges — the `/task 16` loop handles branch + PR.

> **Baseline:** TASK-15 merged and `pytest -q` green; `data/real/mhr-2025-top50.json` present (2,130 games).
> Confirm, then write the failing tests first.

---

## Goal

This is **Phase B2** of [`docs/planning/stage-b-plan.md`](../planning/stage-b-plan.md) — the cheapest
high-value real-data analysis, deliberately sequenced before the prediction surface because it needs **no
probability machinery**, only the cleaned game log and a full-season run of the existing raters.

It answers two questions the synthetic spike could not:
1. **Whose ranking agrees with who-actually-beat-whom?** Reconstruct the head-to-head record among the
   ranked teams (the "gauntlet") and measure how well each model's ordering agrees with it.
2. **Do the real giant-killers get caught?** Put the named schedule-padders under a microscope — bespoke
   vs MHR — with per-game `scheduleTerm` attribution. This is the real-world test of the **S05 thesis**:
   *MHR's published ranking is itself fooled by schedule padding (e.g. Dallas Stars Elite ranked #12 on a
   7-9-1 / −10-goal-diff record against ranked teams); bespoke's orthogonal schedule channel is built to
   discount exactly that.* (See `reports/comparison.md` §4 "Cause 2" and the Stage-B plan B2.)

**This is a full-season single-shot run**, not walk-forward (that is B4). The week field matters only for
the raters' internal recency/tier logic; there is no week iteration here.

**Honesty rule:** the gauntlet is a **proxy, not ground truth** (real data has no planted key). Report it as
such — agreement with the head-to-head subgraph, scored *and* labelled as a proxy. Compute every number,
assert none. Do not score against MHR's *own* published rating (circular — MHR is a candidate); score
against **outcomes** (the head-to-head record).

---

## Two things settled here (do not re-debate)

1. **The ranked set = the 50 teams in the dump; the gauntlet uses intra-ranked games only.** "Points% vs
   ranked" counts only the 1,044 games where **both** teams are in the top-50 set. Gauntlet score per team =
   `(2·w + t) / (2·n) · 100` over intra-ranked games, tie-broken by intra-ranked goal differential — the
   exact metric from the league-intel prototype. Outside-team games are excluded from the *gauntlet* (they
   are not head-to-head among the ranked) but remain in the **raters'** input (schedule strength).

2. **Agreement is measured with Spearman ρ between each model's ranking (restricted to the ranked set) and
   the gauntlet ranking.** Higher = better agreement with who-beat-whom. Report bespoke vs mhr_replica
   side-by-side; the comparative story is the point. (Reuse the harness's existing Spearman helper if it is
   import-safe without pulling in synthetic-only deps; otherwise a small local Spearman is fine — note which.)

---

## Validated real-world oracle (the league-intel numbers — use as test anchors)

From the head-to-head reconstruction (cross-checked both directions, fully symmetric):
- **Dallas Stars Elite** — MHR rank **#12**; overall 48-12-1, +228 GD, **but vs ranked 7-9-1, −10 GD**,
  44.1% gauntlet points; 41-3-0 (93.2%) vs unranked; lowest SOS in the group. Its 7 ranked wins came
  against teams ranked **below** it (Ohio #16, Chicago Reapers #17, North Jersey #15) while it was swept by
  Florida Alliance (2-14), St Louis (0-3), Buffalo (0-2). The textbook real S05.
- **Biggest gauntlet fallers vs MHR rank:** South Shore Kings #10 → ~#16 (−6), Top Gun #11 → ~#17 (−6) —
  schedule-inflated.
- **Biggest climbers:** Florida Surf #20 → ~#14 (+6), St Louis #13 → ~#9 (+4), Ohio #16 → ~#12 (+4).
- Middlesex Islanders East — #1, 37-0-1 vs ranked (98.7%) — the unambiguous top, an anchor for "everyone
  agrees here."

(These come from the earlier top-20 intel build; the TASK-15 dataset is top-50, so exact ranks may shift,
but Dallas's ranked-vs-unranked split and the padder/climber *direction* are the stable oracle. Assert
directions and the Dallas split, not brittle exact ranks.)

---

## Read first

1. **`CLAUDE.md`** — prime directive (explain *why*/behaviour in plain English; tests are the proof);
   determinism (I8 — no RNG, stable sort, byte-identical report); observed-vs-derived wall (gauntlet is
   computed from the log, never a rating fed back).
2. **`docs/planning/stage-b-plan.md`** — Phase **B2** (this task), and why it precedes B3 (no prediction
   surface needed). Also the **graph-connectivity watch-item** (B1): outside teams have 1–2 games, so their
   ratings are noisy — this task evaluates the **top-50 only**, which sidesteps that, but note it.
3. **`reports/comparison.md`** §4 — the S05 "Cause 2" structural story this task tests on real data.
4. **`data/real/mhr-2025-top50.json`** (TASK-15) — the input. 2,130 games; `team`/`opponent` by name; the
   50 ranked teams are the dump's `teams` (verify the array order vs MHR rank before relying on it).
5. **`models/bespoke.py`** (`rate_weekly`) and **`models/mhr_replica.py`** — the raters to run full-season;
   their return shape (ratings per team) → sort to a ranking. **Consume, do not edit.**
6. The league-intel prototype `mhr-league-intel.html` (in the human's Downloads) — the source of the
   gauntlet metric and the validated numbers above, for reference.

---

## Approach (TDD — failing tests first)

### Step 1 — `analysis/test_head_to_head.py`
```python
# test_gauntlet_points_formula: hand-built tiny log → points% = (2w+t)/(2n)*100 exactly; GD tiebreak.
# test_gauntlet_uses_intra_ranked_only: a game vs an outside team does NOT affect any gauntlet score.
# test_agreement_spearman: a model ranking identical to the gauntlet → ρ = 1.0; a known inversion → the
#                          expected lower ρ.
# test_dallas_split_recovered: on the real dataset, the Dallas-equivalent team shows a losing ranked
#                          record + strongly positive unranked record (the padding signature), and its
#                          gauntlet rank is well below its raw win-total rank.
# test_report_is_deterministic: building twice → byte-identical reports/real-h2h.md.
```

### Step 2 — implement `analysis/head_to_head.py`
- `gauntlet_table(games, ranked_set) -> {team: {w,l,t,gf,ga,pts}}` over intra-ranked games; `gauntlet_rank`
  by `(pts desc, gd desc)`.
- `model_ranking(rate_fn, games, ranked_set) -> [teams ordered]` — run the rater full-season on the **full**
  log (outside teams included for schedule strength), then restrict + sort to the ranked set.
- `agreement(model_rank, gauntlet_rank) -> spearman`.
- `case_study(team, games) -> {ranked_record, unranked_record, per_game_attribution}` for the named padders
  (pull bespoke's per-game `scheduleTerm` so the report can show *why* bespoke discounts the lucky wins).
- `build_report(...) -> str` — deterministic markdown.

### Step 3 — `reports/real-h2h.md` (generated, deterministic)
- **Agreement table:** bespoke vs mhr_replica Spearman ρ against the gauntlet (the headline — does bespoke
  agree with who-beat-whom more than the replica?).
- **Mover table:** biggest risers/fallers from MHR rank → gauntlet rank (South Shore, Top Gun, Florida Surf,
  St Louis, Ohio).
- **Case studies:** Dallas (+ South Shore, Top Gun) — ranked vs unranked split, and bespoke's per-game
  schedule attribution showing the lucky wins debited. Plainly labelled: gauntlet is a **proxy**, not truth.
- One-line scope note: full-season single-shot run; walk-forward prediction is B4.

### Step 4 — verify
`python -m analysis.head_to_head` regenerates the report; `pytest -q` green; `ruff check .` clean; second
run → empty `git diff` on the report (byte-identical).

---

## Acceptance / Definition of done

- [ ] New `analysis/` package (`head_to_head.py` + tests), written test-first.
- [ ] Gauntlet table computed from intra-ranked games only; agreement = Spearman(model rank, gauntlet rank),
      bespoke vs mhr_replica, **computed not asserted**.
- [ ] `reports/real-h2h.md` generated deterministically (byte-identical on re-run): agreement headline,
      mover table, and Dallas/giant-killer case studies with bespoke per-game schedule attribution.
- [ ] The Dallas padding signature is demonstrated (losing ranked record + dominant unranked record; gauntlet
      rank ≪ raw-win rank), and the report states whether bespoke ranks it more sensibly than the replica —
      **whatever the numbers say** (honest-fallback; the gauntlet is labelled a proxy, not ground truth).
- [ ] `models/*`, `ingest/*`, `harness/*`, `generator/*`, `scenarios/*`, `core/*` untouched.
- [ ] `pytest -q` green; `ruff check .` clean.
- [ ] **`spec-keeper`** on the diff — confirm: gauntlet computed from the log (observed-vs-derived wall
      intact), scored against *outcomes* not MHR's own rating (no circular validation), determinism
      preserved. (`invariant-auditor` not required — no model change; note in PR.)
- [ ] `docs/work/BOARD.md` row 16 flipped by the loop; the Stage-B plan B2 marked started.
- [ ] PR body (plain English): *why* (real data has no planted truth, so we test agreement with who-beat-whom
      and microscope the real giant-killers), *what was produced* (agreement headline + Dallas case study),
      and the honest verdict — explicitly noting the gauntlet is a proxy and this is single-shot, not
      walk-forward.

---

## Out of scope

- **Walk-forward prediction, log-loss, calibration, the probability surface** — those are Stage-B phases
  B3–B6, separate tasks. This task is full-season, descriptive, no prediction.
- **Any model/rater change.** Consume bespoke + mhr_replica as-is.
- **Scoring against MHR's published rating** (circular). Score against the head-to-head record only.
- **Fixing graph connectivity / fetching more teams** — a B1 follow-on if the backtest later needs it;
  this task evaluates the top-50 set, which is well-connected internally.
- **The TS port / hosted demo** — Phase B7.
