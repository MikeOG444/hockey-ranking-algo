# Stage B — Real-Data Backtest Plan

**Goal of Stage B:** prove the chosen model on *real* MyHockey Rankings data — that it **predicts the
unknown future** at least as well as the MHR incumbent, **stays fair and deterministic on messy real
schedules**, and tells a story a hockey parent can read. Stage A proved *correctness against truth we
control*; Stage B proves *usefulness against truth we don't*.

This plan mirrors [`PLAN.md`](PLAN.md) (which scoped Stage A). It is the productionalization arc the spike
deferred — see `PLAN.md` "Explicitly out of scope" and the brief's
[§10 Stage B](../knowledge-bank/rating-model-test-brief.md).

**The mental shift from Stage A.** Stage A asked *"does it recover the right ordering against a planted
truth key?"* — scored with Spearman vs `groundTruth`. Real data has **no planted truth**, so Stage B asks a
different question — *"does it predict next week's games, and is it still fair?"* — scored with
**log-loss / calibration / score-RMSE** on out-of-sample weeks. Different question, different machinery.

**What carries over unchanged:** the fairness floor and all I1–I13 mechanisms, determinism (I8/I9), the
observed-vs-derived wall (brief §5), and the `rate(games)` interface. Stage B *adds* a prediction surface
and a backtest harness around the settled model — it does **not** re-open the model core.

---

## Decisions locked

- **Stack:** still Python (numpy/scipy/pandas, pytest) for the backtest. TS port is the demo build (Phase
  B7), after the model earns it.
- **Incumbent baseline:** the MHR replica (and its real published ranking, which we have in the data) is the
  bar to clear — "better" stays *measured, not asserted*.
- **Honesty rule unchanged:** compute every verdict, never assert it; no cherry-picking the scenario/team
  set (the `reports/comparison.md` §4 ethos carries into Stage B).
- **Method unchanged:** tests first. Each new metric and the walk-forward engine get failing tests before
  implementation.

---

## The dependency spine (why the order is what it is)

```
B1 data ──► B2 head-to-head + case studies (no prediction surface needed — cheapest win)
   └──────► B3 prediction surface ──► B4 walk-forward engine ──► B5 prediction metrics
                                                                      └──► B6 trust layer (invariants + calibration + churn)
                                                                              └──► B7 recommendation + demo
```

The non-obvious gate is **B3**: bespoke currently emits *ratings, not probabilities*, and **every** Stage-B
accuracy metric (log-loss, Brier, calibration) needs a probability. Nothing in B4/B5/B6 works until B3
exists. B2 is sequenced first precisely because it needs *none* of that — it pays off the real-world
schedule-padding story immediately on the cleaned data.

---

## Phase B1 — Real data into Level-0 (TASK-15, in progress)

Convert the top-50 per-team dump into one deterministic §8 Level-0 dataset + a quality report. Validated
dedup (per-team listing → one row per physical game, 2,130 games), derived `week` + year, outside teams
kept for schedule strength. See [`docs/work/tasks/TASK-15-real-data-loader.md`](../work/tasks/TASK-15-real-data-loader.md).

⚠ **Watch-item — graph connectivity.** The brief calls for *"broad — not just top-20; you need the
connected graph."* The current dump is top-50 + their 215 immediate opponents at **1–2 games each** — a
*weakly* connected graph. Outside-team ratings will be unstable and strength won't propagate cleanly across
clusters. **Before trusting B4/B5 numbers, assess connectivity** (largest connected component, min games per
rated team); a broader pull (more teams / another schedule hop) may be a prerequisite. Tracked as a B1
follow-on if the backtest proves under-connected.

## Phase B2 — Head-to-head agreement + named case studies (TASK-16, next)

The cheapest high-value analysis: it needs **no prediction surface**, only the cleaned log.
- **Gauntlet agreement:** for the top-N teams, reconstruct the head-to-head record web and measure how well
  each model's ordering agrees with who-beat-whom (the "gauntlet re-rank" from the league-intel prototype).
- **Padding case studies:** put the real S05 giant-killers — **Dallas Stars Elite** (7-9-1 / −10 GD vs
  ranked, 41-3 vs unranked, lowest SOS), **South Shore Kings**, **Top Gun** — under a microscope, bespoke
  vs MHR, with per-game `scheduleTerm` attribution. This is the demo's qualitative spine and the direct
  real-world test of the S05 thesis: *MHR's published ranking is itself fooled by schedule padding; bespoke's
  schedule channel is built to catch it.*

## Phase B3 — Prediction surface (the gateway build)

Add a **rating → outcome** link to the common model interface so any rater can predict:
- **Win/loss:** a logistic link on the rating gap, `P(A beats B) = σ(k·(r_A − r_B))`, with `k` fit on the
  backtest's own training weeks (never the test week).
- **Score (optional, for RMSE):** a Poisson/Dixon–Coles expected-goals map from the attack/defense channels.
- Deterministic, pure, no leakage. Unit-tested against hand-worked cases.

## Phase B4 — Walk-forward backtest engine

Week-by-week: at each week W, rate on games **through W only**, predict week W+1, record predictions,
advance. No future leakage (the `week` field from B1 enforces the boundary). Deterministic and resumable;
the MHR replica runs the same loop as incumbent.

## Phase B5 — Prediction metrics (the honest yardstick)

Replace Spearman-vs-truth with out-of-sample prediction scoring:
- **Log-loss + Brier** on win/loss, **RMSE** on predicted scores (Poisson path).
- Per-model, per-week and aggregate; MHR replica as the baseline column.
- A committed, deterministic `reports/backtest.md` artifact (same byte-identical discipline as
  `comparison.md`).

## Phase B6 — Trust layer (fair *and* stable on real noise)

- **Invariants on real data:** re-run the I1–I13 harness MATRIX against the real log. Do the fairness floor
  (I1) and determinism (I8/I9) survive messy schedules, blowouts, and disconnected clusters? This is novel
  confirmation Stage A could not give.
- **Calibration:** reliability curve — do stated 70% chances win ~70%? (brief §6).
- **Churn vs prediction trade-off + tier-freeze sweep** (brief §10 "tier-freeze tuning"): sweep the frozen
  window (1→4 weeks) and decay shape; score on **prediction** (log-loss) *and* **churn** (week-to-week rank
  volatility). Find the shortest window that predicts well without thrashing — the real-data validation of
  I13 that Stage A could only stage synthetically.

## Phase B7 — Recommendation + explainable demo

- **Written recommendation:** *this model, these params, this evidence* — Stage-A invariant grid + Stage-B
  prediction win + the padding case studies — vs the MHR incumbent and its published ranking.
- **TS port + hosted demo:** per-game attribution and a weekly-delta decomposition "a hockey parent can
  read." The league-intel HTML is the working prototype.

---

## Definition of done (Stage B)

1. Real Level-0 dataset + quality report (B1), connectivity assessed.
2. Head-to-head agreement + Dallas/giant-killer case studies show bespoke's schedule channel behaving as
   designed on real data (B2).
3. Walk-forward backtest: bespoke is **competitive-or-better than the MHR replica on prediction** (log-loss
   / calibration / score-RMSE) on out-of-sample weeks (B3–B5).
4. I1–I13 still hold on the real log; calibration is sane; the tier-freeze window predicts without thrashing
   (B6).
5. Written recommendation + an explainable, hosted demo (B7).

---

## Risks / watch-items

- **Graph connectivity (B1)** — a top-50-centric dump may be too sparse beyond the top teams for stable
  ratings; assess before trusting backtest numbers.
- **Prediction-surface leakage (B3/B4)** — the link parameter `k` and any calibration must be fit on
  training weeks only; a single leaked future game invalidates the backtest.
- **No-ground-truth temptation** — with no planted key, it is tempting to score against MHR's own ranking
  (circular — MHR is a candidate). Score against *outcomes* (prediction), not against another rater.
- **Determinism on real data** — wall-clock dates, doubleheaders, and ties must not introduce order
  dependence; the I8/I9 guards from Stage A must be re-asserted on the real log (B6).
- **Demo over-claiming** — the hosted story must report the honest verdict (including any loss), not a
  curated win.
