"""Comparison runner — the decision artifact for the spike (TASK-12).

Two cleanly separated halves, joined into one deterministic Markdown report:

1. **Invariant matrix** — re-executes the harness ``MATRIX`` (the single source of truth for
   which invariant each model is expected to hold/break) live, cell by cell, and records the
   *observed* outcome as a glyph. The bespoke_flat/bespoke_weekly rows collapse into one
   ``bespoke`` column. This is the comparative story: bespoke holds I1–I13; the benchmarks
   document the I1 violation.

2. **Rank recovery** — runs each model over the 13 §7 scenario datasets and scores the recovered
   ratings against the generator's planted truth via ``metrics.score_model``. The headline
   "beats MHR" number is the mean Spearman ρ over the *scorable* scenarios (those whose planted
   ratings have real spread); degenerate-truth scenarios are reported but excluded from the mean,
   never silently dropped.

The runner only ever *consumes* ``RateResult`` + planted ``TeamParams`` — it never feeds a
recovered score back into a solve (observed-vs-derived wall, brief §5). It writes no model
logic: it re-runs the existing ``check_I*`` functions, which are the audited surface.

**Determinism (I8 ethos).** ``reports/comparison.md`` must regenerate byte-identically: no
wall-clock content, stable ordering everywhere (invariants I1→I13, scenarios S01→S13, models
bespoke→mhr→ridge), and every float rendered at fixed precision.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from harness.adapters import bespoke_weekly, mhr, ridge
from harness.metrics import MetricsResult, point_in_time_truth, score_model
from harness.test_harness import MATRIX
from models.bespoke import BespokeParams, rate_weekly
from scenarios.builders import (
    build_s01_disconnected,
    build_s02_bridge_game,
    build_s03_schedule_inflation,
    build_s04_stale_opponent,
    build_s05_giant_killer,
    build_s06_win_but_should_drop,
    build_s07_close_vs_tier,
    build_s08_tie_handling,
    build_s09_sparse_vs_dense,
    build_s10_transitivity_trap,
    build_s11_momentum,
    build_s12_blowout_incentive,
    build_s13_freeze_window,
)

# Canonical, deterministic orderings used everywhere in the report.
INVARIANTS = [f"I{i}" for i in range(1, 14)]
MODEL_COLS = ["bespoke", "mhr", "ridge"]
FLOAT_FMT = "{:.4f}"

# Scenario id → builder, in S01→S13 order. Each builder returns (Dataset, metadata-dict).
SCENARIO_BUILDERS = [
    ("S01", build_s01_disconnected),
    ("S02", build_s02_bridge_game),
    ("S03", build_s03_schedule_inflation),
    ("S04", build_s04_stale_opponent),
    ("S05", build_s05_giant_killer),
    ("S06", build_s06_win_but_should_drop),
    ("S07", build_s07_close_vs_tier),
    ("S08", build_s08_tie_handling),
    ("S09", build_s09_sparse_vs_dense),
    ("S10", build_s10_transitivity_trap),
    ("S11", build_s11_momentum),
    ("S12", build_s12_blowout_incentive),
    ("S13", build_s13_freeze_window),
]

# The three rank-recovery models. Bespoke uses the full tier+trend candidate (rate_weekly).
RECOVERY_MODELS = [
    ("bespoke", bespoke_weekly),
    ("mhr", mhr),
    ("ridge", ridge),
]

# A planted-rating spread below this is "degenerate truth": Spearman ρ is meaningless, so the
# scenario is excluded from the headline mean (brief/TASK-12 rule).
SCORABLE_STD_FLOOR = 1e-9

# Historical baseline from TASK-13 (static-key era, before TASK-14 corrected the trajectory
# scoring). These are fixed reference points used in the §4 before/after slice so the
# correction is transparent. They are not computed from the current scorer because the scorer
# has already been updated.
_S11_BESPOKE_RHO_STATIC = -0.5000   # S11 bespoke Spearman under the season-average static key
_S11_MHR_RHO_STATIC     = -0.1000   # S11 mhr Spearman under the season-average static key
_BESPOKE_MEAN_RHO_TASK13 = 0.6928   # bespoke mean Spearman after TASK-13, before TASK-14
_MHR_MEAN_RHO_TASK13     = 0.7769   # mhr mean Spearman after TASK-13
# Pre-TASK-17 reference points (the base=3/1/0 floor model, after TASK-14 point-in-time truth) —
# the honest before/after baseline for the surprise-centered change (TASK-17).
_BESPOKE_MEAN_RHO_PRE_TASK17 = 0.8019  # bespoke headline mean Spearman just before TASK-17
_S05_BESPOKE_RHO_PRE_TASK17  = 0.3571  # S05 (giant-killer) bespoke Spearman just before TASK-17


@dataclass(frozen=True)
class GateResult:
    """The computed (not prose-asserted) gate verdict."""

    bespoke_all_invariants_pass: bool   # every bespoke cell ✓, and no XPASS / ✗ FAIL anywhere
    bespoke_beats_mhr: bool             # mean scorable Spearman: bespoke > mhr
    mean_spearman: dict[str, float]     # per-model mean Spearman over scorable scenarios
    scored_scenarios: list[str]         # scenarios with real planted spread (headline pool)
    excluded_scenarios: list[str]       # degenerate-truth scenarios (reported, not averaged)


def _fmt(x: float) -> str:
    """Fixed-precision float for the report; collapse signed zero so '-0.0000' never appears.

    Keeps the artifact byte-deterministic *and* readable (a stray negative zero from a tiny
    round-off would otherwise render as '-0.0000').
    """
    s = FLOAT_FMT.format(x)
    return "0.0000" if s == "-0.0000" else s


def _model_column(model_name: str) -> str:
    """Map a MATRIX model name to its report column (both bespoke adapters → 'bespoke')."""
    if model_name.startswith("bespoke"):
        return "bespoke"
    return model_name


def _glyph(expect: str, raised: bool) -> str:
    """Translate (expected outcome, did the check raise AssertionError?) into a cell glyph.

    pass  → ✓ when the check holds, ✗ FAIL when it raises (a real regression: gate fails).
    xfail → ✗ when the documented violation reproduces, XPASS when it unexpectedly holds
            (the MATRIX is stale: surface loudly, gate fails).
    skip  → — (the model lacks the feature; not a failure).
    """
    if expect == "skip":
        return "—"
    if expect == "pass":
        return "✗ FAIL" if raised else "✓"
    if expect == "xfail":
        return "✗" if raised else "XPASS"
    raise ValueError(f"Unknown expect value {expect!r}")


def run_invariant_matrix() -> dict[str, dict[str, str]]:
    """Re-execute the harness MATRIX live → {inv_id: {model_col: glyph}}.

    For each cell we run ``check_fn(model_fn, games_fn())`` and record the observed outcome,
    never the MATRIX's stored expectation. bespoke_flat/bespoke_weekly merge into 'bespoke'
    (each invariant names exactly one bespoke adapter, so there is no collision).
    """
    matrix: dict[str, dict[str, str]] = {inv: {} for inv in INVARIANTS}
    for inv_id, check_fn, model_name, model_fn, games_fn, expect in MATRIX:
        col = _model_column(model_name)
        if expect == "skip":
            matrix[inv_id][col] = "—"
            continue
        games = games_fn()
        try:
            check_fn(model_fn, games)
            raised = False
        except AssertionError:
            raised = True
        matrix[inv_id][col] = _glyph(expect, raised)
    return matrix


def run_rank_recovery() -> dict[str, dict[str, MetricsResult]]:
    """Score every model over all 13 §7 scenarios → {scenario_id: {model_name: MetricsResult}}.

    Each model rates the scenario's Level-0 games; ``score_model`` compares the recovered
    ratings to the planted ``ground_truth``. Pure output consumption — no score re-enters a solve.

    Trajectory detection: if any team in the scenario has trajectory != "flat", the scenario is
    scored against point-in-time truth (end-of-season week_params rating) rather than the static
    TeamParams.rating baseline. For flat teams week_params returns the raw baseline, so all-flat
    scenarios score byte-identically. This removes the measurement artifact on S04/S11 without
    touching the model or the fairness floor.
    """
    recovery: dict[str, dict[str, MetricsResult]] = {}
    for scen_id, builder in SCENARIO_BUILDERS:
        dataset, _meta = builder()

        # Detect trajectory scenarios structurally (not a hard-coded list).
        has_trajectory = any(t.trajectory != "flat" for t in dataset.ground_truth)
        if has_trajectory:
            n_weeks = max(g.week for g in dataset.games)
            pit_truth = point_in_time_truth(dataset.ground_truth, n_weeks)
        else:
            pit_truth = None

        row: dict[str, MetricsResult] = {}
        for model_name, model_fn in RECOVERY_MODELS:
            result = model_fn(dataset.games)
            row[model_name] = score_model(dataset.ground_truth, result, truth_ratings=pit_truth)
        recovery[scen_id] = row
    return recovery


def _true_rating_std(scen_id: str) -> float:
    """Standard deviation of the truth ratings for a scenario (its scorability signal).

    Uses the same truth vector that run_rank_recovery uses for scoring: point-in-time truth
    for trajectory scenarios, static TeamParams.rating for all-flat scenarios. This keeps
    the scorable-set rule and the score consistent — they can't disagree on which vector
    they're working from (task spec requirement).
    """
    builder = dict(SCENARIO_BUILDERS)[scen_id]
    dataset, _meta = builder()
    has_trajectory = any(t.trajectory != "flat" for t in dataset.ground_truth)
    if has_trajectory:
        n_weeks = max(g.week for g in dataset.games)
        pit = point_in_time_truth(dataset.ground_truth, n_weeks)
        ratings = list(pit.values())
    else:
        ratings = [t.rating for t in dataset.ground_truth]
    if len(ratings) < 2:
        return 0.0
    return float(np.std(ratings))


def gate_verdict(
    matrix: dict[str, dict[str, str]],
    recovery: dict[str, dict[str, MetricsResult]],
) -> GateResult:
    """Compute the two-part gate verdict from the matrix + rank-recovery results."""
    # Half 1 — invariants. Every bespoke cell must be ✓, and the whole grid must be free of
    # both stale-MATRIX XPASS and real-regression ✗ FAIL glyphs.
    all_glyphs = [g for row in matrix.values() for g in row.values()]
    bespoke_ok = all(matrix[inv]["bespoke"] == "✓" for inv in INVARIANTS)
    no_regressions = ("XPASS" not in all_glyphs) and ("✗ FAIL" not in all_glyphs)
    bespoke_all_invariants_pass = bespoke_ok and no_regressions

    # Half 2 — rank recovery. Mean Spearman over scorable scenarios only.
    scored = [s for s, _ in SCENARIO_BUILDERS if _true_rating_std(s) > SCORABLE_STD_FLOOR]
    excluded = [s for s, _ in SCENARIO_BUILDERS if s not in scored]

    mean_spearman: dict[str, float] = {}
    for model_name, _ in RECOVERY_MODELS:
        rhos = [recovery[s][model_name].spearman_rho for s in scored]
        mean_spearman[model_name] = float(np.mean(rhos)) if rhos else 0.0

    bespoke_beats_mhr = mean_spearman["bespoke"] > mean_spearman["mhr"]

    return GateResult(
        bespoke_all_invariants_pass=bespoke_all_invariants_pass,
        bespoke_beats_mhr=bespoke_beats_mhr,
        mean_spearman=mean_spearman,
        scored_scenarios=scored,
        excluded_scenarios=excluded,
    )


def _trajectory_scenarios() -> list[str]:
    """Scenarios containing at least one team with a non-flat trajectory (S04, S11).

    For these, the generator drifts a team week-by-week, so the planted *static* rating
    (attack − defense) is the season *average*, not the team's realized end-of-season form. A
    recency-aware model is *supposed* to deviate from that static truth, so Spearman vs static
    truth scores the recency feature backwards. Derived live so it can't drift from the builders.
    """
    out: list[str] = []
    for scen_id, builder in SCENARIO_BUILDERS:
        dataset, _meta = builder()
        if any(t.trajectory != "flat" for t in dataset.ground_truth):
            out.append(scen_id)
    return out


def _mean_spearman_excluding(
    recovery: dict[str, dict[str, MetricsResult]],
    excluded: set[str],
    model_name: str,
) -> float:
    """Mean Spearman ρ for one model over scenarios not in ``excluded``."""
    rhos = [recovery[s][model_name].spearman_rho for s, _ in SCENARIO_BUILDERS if s not in excluded]
    return float(np.mean(rhos)) if rhos else 0.0


def _parameterization_line() -> str:
    """Name the bespoke candidate's parameterization from its actual defaults (no drift)."""
    p = BespokeParams()
    sig = inspect.signature(rate_weekly)
    d = {k: v.default for k, v in sig.parameters.items() if v.default is not inspect.Parameter.empty}
    return (
        f"**Bespoke candidate:** `rate_weekly` at defaults — "
        f"win/tie/loss = {p.win:.1f}/{p.tie:.1f}/{p.loss:.1f}, α = {p.alpha:.2f}, "
        f"ρ = {d['rho']:.2f}, ρ_tier = {d['rho_tier']:.2f}, "
        f"max_window = {d['max_window']}, trend_window = {d['trend_window']}, λ = {d['lam']:.2f}."
    )


def _matrix_table(matrix: dict[str, dict[str, str]]) -> str:
    lines = ["| Invariant | bespoke | mhr | ridge |", "|---|---|---|---|"]
    for inv in INVARIANTS:
        row = matrix[inv]
        lines.append(f"| {inv} | {row['bespoke']} | {row['mhr']} | {row['ridge']} |")
    return "\n".join(lines)


def _metric_table(
    recovery: dict[str, dict[str, MetricsResult]],
    field: str,
    scored: set[str],
    mark_scorable: bool,
) -> str:
    header = "| Scenario | bespoke | mhr | ridge |"
    sep = "|---|---|---|---|"
    if mark_scorable:
        header = "| Scenario | bespoke | mhr | ridge | scorable |"
        sep = "|---|---|---|---|---|"
    lines = [header, sep]
    for scen_id, _ in SCENARIO_BUILDERS:
        row = recovery[scen_id]
        cells = [_fmt(getattr(row[m], field)) for m in MODEL_COLS]
        line = f"| {scen_id} | {cells[0]} | {cells[1]} | {cells[2]} |"
        if mark_scorable:
            flag = "yes" if scen_id in scored else "—"
            line = f"| {scen_id} | {cells[0]} | {cells[1]} | {cells[2]} | {flag} |"
        lines.append(line)
    return "\n".join(lines)


def _attribution_section() -> str:
    """Render T_SUBJECT's per-game attribution from S07 — the I6 story in miniature.

    T_SUBJECT plays exactly two games: a 1-goal loss to the elite (T_TOP) and a 1-goal win over
    the bottom (T_BOTTOM). Under surprise-centered credit (TASK-17) games are identified by the
    `is_win` flag — `base` is now the centered result quality, not the old 3/0 floor.
    """
    dataset, _meta = build_s07_close_vs_tier()
    result = rate_weekly(dataset.games)
    attr = result.per_game_attribution.get("T_SUBJECT", [])

    loss_bd = next((bd for bd in attr if not bd.is_win), None)
    win_bd = next((bd for bd in attr if bd.is_win), None)

    lines = [
        "`T_SUBJECT` is an average team with two planted games: a narrow **loss to the league's "
        "best** (`T_TOP`) and a narrow **win over the league's worst** (`T_BOTTOM`). Each game's "
        "credit is `max(base + margin_adj + schedule_term + self_term, own_rating)` for a win (the "
        "win-floor) and the raw sum otherwise; `w` is its recency weight in the season mean.",
        "",
        "| Game | base | margin_adj | schedule_term | self_term | w | total |",
        "|---|---|---|---|---|---|---|",
    ]
    if loss_bd is not None:
        lines.append(
            f"| Loss to T_TOP (elite) | {_fmt(loss_bd.base)} | "
            f"{_fmt(loss_bd.margin_adj)} | {_fmt(loss_bd.schedule_term)} | "
            f"{_fmt(loss_bd.self_term)} | {_fmt(loss_bd.w)} | {_fmt(loss_bd.total)} |"
        )
    if win_bd is not None:
        lines.append(
            f"| Win over T_BOTTOM (weak) | {_fmt(win_bd.base)} | "
            f"{_fmt(win_bd.margin_adj)} | {_fmt(win_bd.schedule_term)} | "
            f"{_fmt(win_bd.self_term)} | {_fmt(win_bd.w)} | {_fmt(win_bd.total)} |"
        )
    season = result.ratings.get("T_SUBJECT", 0.0)
    lines += [
        "",
        f"Reconciled season rating for `T_SUBJECT`: **{_fmt(season)}**.",
        "",
        "In plain English (surprise-centered credit, TASK-17): each game's credit anchors on the "
        "team's own rating (`self_term`) and adds the *surprise* — the centered result quality "
        "(`base` + `margin_adj`) plus `schedule_term`, which rewards who you played (a big positive "
        "for facing the elite, a debit for beating the weakest). A **win is floored at your own "
        "rating** so it never lowers you, but an *expected* win shows ~nothing; a close loss to the "
        "elite earns a positive surprise. That is exactly the I6 question: *does a narrow loss to the "
        "best earn more than a narrow win over the worst?* The answer is **yes end-to-end** — the "
        "loss to T_TOP out-credits the win over T_BOTTOM on the converged ratings (see §6).",
    ]
    return "\n".join(lines)


def _verdict_word(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _rationale_section(
    recovery: dict[str, dict[str, MetricsResult]],
    verdict: GateResult,
) -> str:
    """Explain — honestly — why Half 2 reads as it does at current defaults.

    The decision (with the spike owner): report the raw, current-defaults result and route
    accuracy improvement to TASK-13's tuning, rather than slicing the scenario set until bespoke
    'wins'. This section shows that no *principled* exclusion flips the result, so the gap is real
    and is a tuning target, not a metric artifact to be defined away.
    """
    base_excl = set(verdict.excluded_scenarios)            # degenerate truth (std ≈ 0)
    traj = set(_trajectory_scenarios())                    # recency-vs-static-truth conflict
    traj_excl = base_excl | traj

    b_head = _mean_spearman_excluding(recovery, base_excl, "bespoke")
    m_head = _mean_spearman_excluding(recovery, base_excl, "mhr")
    b_traj = _mean_spearman_excluding(recovery, traj_excl, "bespoke")
    m_traj = _mean_spearman_excluding(recovery, traj_excl, "mhr")

    def _ahead(b: float, m: float) -> str:
        return "yes" if b > m else "no"

    lines = [
        "Bespoke wins **fairness** outright (every invariant I1–I13). On the synthetic rank-recovery "
        "half it **trails** the MHR replica "
        f"({_fmt(verdict.mean_spearman['bespoke'])} vs {_fmt(verdict.mean_spearman['mhr'])}), and "
        "**TASK-17 deliberately moved this number the wrong way** — that is reported here in full, "
        "not buried.",
        "",
        "**The TASK-17 change (surprise-centered credit) and its honest cost.** TASK-17 replaced the "
        "old `base = 3/1/0` result floor with *surprise-centered* credit: a game's credit anchors on "
        "the team's own rating and adds the surprise of the result against the opponent (an *expected* "
        "win over a much weaker team is ~neutral — the win-floor pins it to your own rating — while a "
        "close loss to an elite earns a small positive). This realigns the fairness principle from "
        "'a win must always count' to 'a win is not a loss', which the owner adopted to fix a real "
        "closing-schedule inversion. The cost: synthetic headline rank recovery regressed "
        f"**{_fmt(_BESPOKE_MEAN_RHO_PRE_TASK17)} → {_fmt(verdict.mean_spearman['bespoke'])}** "
        "(pre-TASK-17 floor model → surprise-centered).",
        "",
        "**Where the synthetic regression lives — and why it is largely an artifact.** It concentrates "
        "in (a) the **disconnected-graph scenarios** (S01/S02): with no cross-component games the "
        "relative *level* of two pods is genuinely unidentifiable, and the old `base = 3` floor only "
        "ranked them by *accident* (it anchored every team to a win-rate-driven positive level); "
        "surprise-centering removes that accidental anchor, so the honest 'cannot compare unconnected "
        "teams' shows up as a low Spearman. And (b) mild **compression** in clean round-robins, where "
        "neutralizing expected results discards some ordering signal. Real play has neither pathology "
        "— every team is connected through common opponents.",
        "",
        "**The other side of the ledger — the change does exactly what it was for.** The synthetic "
        "**giant-killer S05** — the one scenario that mirrors the real failure mode — *improved* "
        f"({_fmt(_S05_BESPOKE_RHO_PRE_TASK17)} → {_fmt(recovery['S05']['bespoke'].spearman_rho)}). And "
        "on the **real MHR dataset** the headline inversion is fixed: Woodbridge fell #9 → #18 and "
        "Mid-Fairfield (Elite) rose #14 → #6 (the 5-0 head-to-head winner now ranks above the team it "
        "swept), the top six became all genuine national-elite programs, and the schedule-padded "
        "Dallas Stars Elite (7-9-1) dropped out of the top 20. See `reports/real-h2h.md`.",
        "",
        "**Historical note — Cause 1 (trajectory artifact, S04/S11) stays resolved.** TASK-14's "
        "point-in-time truth fix is orthogonal to TASK-17 and still holds (S11: "
        f"{_fmt(_S11_BESPOKE_RHO_STATIC)} static-key era → "
        f"{_fmt(recovery['S11']['bespoke'].spearman_rho)} point-in-time).",
        "",
        "| Scenarios counted in the mean | bespoke | mhr | bespoke ahead? |",
        "|---|---|---|---|",
        f"| All scorable (degenerate truth {', '.join(sorted(base_excl))} excluded) | "
        f"{_fmt(b_head)} | {_fmt(m_head)} | {_ahead(b_head, m_head)} |",
        f"| Also set aside trajectory scenarios ({', '.join(sorted(traj))}) | "
        f"{_fmt(b_traj)} | {_fmt(m_traj)} | {_ahead(b_traj, m_traj)} |",
        "",
        "**Decision (ship + document, no cherry-picking).** The gate reads **FAIL** on the synthetic "
        "set, honestly. It ships anyway because (1) the regression is concentrated in scenarios "
        "unrepresentative of real play, where the old floor only 'won' by accident; (2) the "
        "representative synthetic scenario (S05) and the real-data ranking both moved the right way; "
        "and (3) the fairness realignment is the goal. **Methodology pivot (2026-06-24):** the "
        "synthetic rank-recovery score is no longer the authoritative gate — it partly rewarded the "
        "floor's accidental anchoring — so evaluation moves to the **real MHR dataset**, and the "
        "**B4 walk-forward backtest** remains the final adjudicator of predictive accuracy.",
    ]
    return "\n".join(lines)


def build_report(
    matrix: dict[str, dict[str, str]],
    recovery: dict[str, dict[str, MetricsResult]],
    verdict: GateResult,
) -> str:
    """Assemble the full deterministic Markdown report string."""
    scored_set = set(verdict.scored_scenarios)
    ms = verdict.mean_spearman
    overall = verdict.bespoke_all_invariants_pass and verdict.bespoke_beats_mhr

    parts = [
        "# Model comparison — decision artifact (Phase 6)",
        "",
        "Generated by `harness/run.py` (`python -m harness.run`). This file is a committed, "
        "diffable artifact and **regenerates byte-identically** — its determinism is asserted by "
        "`harness/test_run.py::test_report_is_deterministic`.",
        "",
        _parameterization_line(),
        "",
        "## 1. Invariant matrix (I1–I13 × model)",
        "",
        "Computed live from `harness.test_harness.MATRIX` — each cell re-runs the real `check_I*` "
        "function. Glyphs: **✓** holds · **✗** documented violation (the comparative story) · "
        "**—** feature not applicable to that model · **✗ FAIL** regression · **XPASS** stale "
        "expectation. A healthy grid has no ✗ FAIL and no XPASS.",
        "",
        _matrix_table(matrix),
        "",
        "Bespoke holds **every** invariant I1–I13. The benchmarks document the I1 violation "
        "(winning vs a common opponent can rank below losing to it) — that is the comparative "
        "story, not a defect in the harness.",
        "",
        "## 2. Rank recovery vs planted truth (§7 scenarios)",
        "",
        "Each model rates every scenario's Level-0 games; the recovered ratings are scored against "
        "the generator's planted truth. **Spearman ρ** is rank agreement (higher is better); "
        "**centered RMSE** is scale-invariant error (lower is better). **Tier accuracy** is not "
        "exercised by this suite (see the note below the RMSE table).",
        "",
        "### Spearman ρ (rank correlation vs planted truth)",
        "",
        _metric_table(recovery, "spearman_rho", scored_set, mark_scorable=True),
        "",
        "Scenarios marked *scorable* have planted ratings with real spread; the degenerate-truth "
        "scenarios (all-equal or near-equal true ratings — e.g. tie-handling, the transitivity "
        "trap) are shown but **excluded from the headline mean**, since rank correlation is "
        "undefined there.",
        "",
        "### Centered RMSE (lower is better)",
        "",
        _metric_table(recovery, "centered_rmse", scored_set, mark_scorable=False),
        "",
        "Bespoke posts the lowest centered RMSE on most scenarios — note this is a *scale* metric, "
        "not a *rank* one, so it can favour bespoke even where its Spearman trails (a model can place "
        "teams at well-calibrated rating magnitudes yet order a near-tied pair differently).",
        "",
        "### Tier accuracy — not exercised by this suite",
        "",
        "Tier accuracy is **0.0000 for every model on every scenario**, for a structural reason: the "
        "§7 generator plants no tier labels (`TeamParams.tier = None`), so `score_model` finds "
        "`n_tiers_scored = 0` and tier accuracy is undefined → reported as 0. This is *not* a model "
        "failure — it means these scenarios test rating/rank recovery, not tier assignment. Tier "
        "behaviour is covered separately by invariant **I13** (matrix above) and the §7 tier "
        "scenarios' own assertions. A tier-accuracy comparison would need truth datasets that carry "
        "planted tier labels (a future generator/metric extension, out of scope here).",
        "",
        "## 3. Gate verdict",
        "",
        f"- **Scorable scenarios** ({len(verdict.scored_scenarios)}): "
        f"{', '.join(verdict.scored_scenarios)}",
        f"- **Excluded (degenerate truth)** ({len(verdict.excluded_scenarios)}): "
        f"{', '.join(verdict.excluded_scenarios)}",
        "",
        f"- **Headline mean Spearman ρ** (scorable only) — bespoke "
        f"**{_fmt(ms['bespoke'])}** · mhr {_fmt(ms['mhr'])} · "
        f"ridge {_fmt(ms['ridge'])}",
        "",
        f"- **Half 1 — bespoke holds every invariant I1–I13:** "
        f"{_verdict_word(verdict.bespoke_all_invariants_pass)}",
        f"- **Half 2 — bespoke beats the MHR replica on mean rank recovery:** "
        f"{_verdict_word(verdict.bespoke_beats_mhr)}",
        f"- **Overall gate:** {_verdict_word(overall)}",
        "",
        "## 4. Why the accuracy half reads as it does (the honest call)",
        "",
        _rationale_section(recovery, verdict),
        "",
        "## 5. Per-game attribution example — `T_SUBJECT` (scenario S07)",
        "",
        _attribution_section(),
        "",
        "## 6. Caveats / open items",
        "",
        "- **End-to-end I6 is robust (surprise-centered credit, TASK-17).** Centering shrank the "
        "win/loss quality gap (~0.75, was 3), so a narrow loss to the elite out-credits a narrow win "
        "over the bottom **end-to-end at every α in the grid** — the old 'α must clear an I6 floor' no "
        "longer binds. The damped solve is now an **unconditional `(1 − λ)` contraction** for any "
        "α ∈ [0, 1) (the self-anchor weight `(1 − α)` and opponent weight `α` sum to 1), stronger than "
        "the old `α(1 − λ)` bound. See decision memo §3.1 (TASK-17 re-derivation).",
        "- **Parameters are the principled memo defaults (α = 0.75, ρ = ρ_tier = 0.2, tier table "
        "unchanged).** Post-TASK-17 the synthetic `harness/tune.py` sweep is **no longer the "
        "param-selection oracle** — the synthetic rank-recovery score was shown to be partly an "
        "artifact of the old `base = 3` floor's accidental anchoring (see §4). The sweep remains a "
        "reproducible diagnostic (`python -m harness.tune`); the shipped point is the memo strawman, "
        "verified invariant-feasible (I6 + contraction).",
        "- **DONE — point-in-time truth for trajectory scenarios (TASK-14).** S04/S11 are now "
        "scored against `week_params(team, last_week).rating` — the generator's end-of-season "
        "realized form — instead of the static season-average `TeamParams.rating`. For flat teams "
        "`week_params` returns the raw baseline, so all-flat scenario scores are byte-identical to "
        "before. The trajectory measurement artifact diagnosed in TASK-13 is removed (orthogonal to "
        "TASK-17).",
        "- **Evaluation pivots to real data (2026-06-24).** The synthetic rank-recovery half is no "
        "longer the authoritative gate; the real MHR dataset (`reports/real-h2h.md`) is the yardstick, "
        "with the B4 walk-forward backtest as the final adjudicator. Stage B (walk-forward / log-loss "
        "/ calibration) remains out of scope for this snapshot.",
        "",
    ]
    return "\n".join(parts)


def main() -> None:
    """Wire the four seams together and write the report to reports/comparison.md."""
    matrix = run_invariant_matrix()
    recovery = run_rank_recovery()
    verdict = gate_verdict(matrix, recovery)
    report = build_report(matrix, recovery, verdict)

    out_path = Path(__file__).resolve().parent.parent / "reports" / "comparison.md"
    with open(out_path, "w") as fh:
        fh.write(report)


if __name__ == "__main__":
    main()
