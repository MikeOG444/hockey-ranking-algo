# TASK-19: Migrate the evaluation gate from synthetic to real data

**State:** refined · **Model:** **sonnet** — evaluation/reporting plumbing, not model-core.
**Owns (files):** a new real-data evaluation entry point under `harness/` (e.g. `harness/real_gate.py` +
tests); consumes `ingest/` + `analysis/`; new/updated `reports/`. **Does NOT touch `models/bespoke.py`.**
**Parallel-safe:** yes (additive; no model-core overlap).
**Depends on:** TASK-15 (real loader), TASK-16 (head-to-head/case studies), TASK-17 (the model change that
triggered the pivot).

---

## Why this exists (owner direction, 2026-06-24)

During TASK-17 the synthetic §7 rank-recovery score regressed (0.8019 → 0.7031) even though the change
fixed the real closing-schedule inversion and improved the synthetic giant-killer S05. Investigation
(`reports/comparison.md` §4) showed the synthetic score was **partly an artifact of the old `base=3`
floor's accidental anchoring** — so it is not a trustworthy accuracy gate. The owner's call: **stop using
the synthetic scenarios as the primary gate; evaluate on the real MHR dataset going forward.** See the
memory note `project_eval_on_real_data.md`.

## What to build

1. A **real-data evaluation** that scores each model (bespoke, mhr_replica, ridge_massey) against the real
   MHR signal we actually have — at minimum **head-to-head agreement** (does the rating order respect direct
   results) and **agreement with the published MHR rank order** — reusing `ingest/` + `analysis/`
   primitives. Emit a deterministic report (e.g. `reports/real-eval.md`).
2. Make this the **headline gate artifact**; demote the synthetic suite to **targeted invariant/mechanism
   unit tests** (keep S01–S14 as such — they still guard I1–I13 and specific behaviors). Update
   `reports/comparison.md` / `harness/run.py` framing so the synthetic mean is clearly labeled
   *diagnostic, not gate*.
3. Keep the **B4 walk-forward backtest out of scope** (it remains the eventual predictive adjudicator); this
   task delivers a real-data *ranking-agreement* gate, not a predictive one.

## Constraints

- **Determinism (I8):** the real-data report regenerates byte-identically.
- **Observed-vs-derived wall:** score against real *results* / published ranks; never feed a model's own
  rating back in as truth.
- **No model changes** — consume the models, don't tune them here.

## Definition of done

- [ ] A deterministic real-data evaluation + report scoring all three models on head-to-head agreement and
      published-rank agreement.
- [ ] Synthetic suite explicitly reframed as diagnostic/unit (not the headline gate) in the reports.
- [ ] `pytest -q` green; `ruff check .` clean; report byte-identical on re-run.

## Out of scope

- B4 walk-forward / log-loss / calibration (separate Stage-B task).
- Any `models/bespoke.py` change; any new synthetic scenario (if one is needed later, model it on a real
  case per `project_eval_on_real_data.md`).
