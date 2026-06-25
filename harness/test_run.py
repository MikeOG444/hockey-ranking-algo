"""Tests for the comparison runner (TASK-12).

These pin the public seams of ``harness/run.py``: the live invariant matrix, the
rank-recovery sweep, the computed gate verdict, and the byte-deterministic report.
Every input is built by calling the runner's own (pure) functions — no fixtures.
"""

from harness.metrics import MetricsResult
from harness.run import (
    GateResult,
    build_report,
    gate_verdict,
    run_invariant_matrix,
    run_rank_recovery,
)

ALL_INVARIANTS = {f"I{i}" for i in range(1, 14)}
MODEL_COLS = {"bespoke", "mhr", "ridge"}


def test_invariant_matrix_shape() -> None:
    """The matrix covers I1–I13, each row keyed by the three model columns."""
    m = run_invariant_matrix()
    assert set(m) == ALL_INVARIANTS
    for inv, row in m.items():
        assert set(row) == MODEL_COLS, f"{inv} row keys = {set(row)}"


def test_bespoke_passes_every_invariant() -> None:
    """Core gate: the bespoke candidate holds every invariant I1–I13 (glyph ✓)."""
    m = run_invariant_matrix()
    for inv in ALL_INVARIANTS:
        assert m[inv]["bespoke"] == "✓", f"{inv}: bespoke = {m[inv]['bespoke']}"


def test_benchmarks_show_documented_violations() -> None:
    """Benchmarks document the I1 violation (✗), and nothing is a regression."""
    m = run_invariant_matrix()
    assert m["I1"]["mhr"] == "✗"
    assert m["I1"]["ridge"] == "✗"
    # No stale MATRIX (XPASS) and no real regression (✗ FAIL) anywhere in the grid.
    for inv, row in m.items():
        for col, glyph in row.items():
            assert glyph not in ("XPASS", "✗ FAIL"), f"{inv}/{col} = {glyph}"


def test_rank_recovery_covers_all_scenarios() -> None:
    """Every §7 scenario is scored for all three models, each a MetricsResult."""
    r = run_rank_recovery()
    assert len(r) == 13
    expected_scenarios = {f"S{i:02d}" for i in range(1, 14)}
    assert set(r) == expected_scenarios
    for scen, row in r.items():
        assert set(row) == {"bespoke", "mhr", "ridge"}, f"{scen} model keys = {set(row)}"
        for model, res in row.items():
            assert isinstance(res, MetricsResult), f"{scen}/{model} is {type(res)}"


def test_gate_verdict_is_computed_consistently() -> None:
    """The gate is computed from the evidence, not asserted by prose.

    Half 1 (fairness) genuinely passes — bespoke holds every invariant. Half 2 (accuracy) is
    *not* hard-coded to a win: at current untuned defaults the bespoke candidate has not yet
    beaten the MHR replica on mean Spearman (that is TASK-13's tuning target). We assert the
    boolean is *consistent* with the computed means, not that it is True — letting truth-scoring
    have the final word (CLAUDE.md). We also pin that the degenerate-truth scenarios are recorded,
    never silently dropped.
    """
    v = gate_verdict(run_invariant_matrix(), run_rank_recovery())
    assert isinstance(v, GateResult)
    # Fairness half holds for real.
    assert v.bespoke_all_invariants_pass is True
    # Accuracy half is computed, not assumed: the boolean must equal the mean comparison.
    assert v.bespoke_beats_mhr == (v.mean_spearman["bespoke"] > v.mean_spearman["mhr"])
    # Degenerate-truth scenarios are surfaced (no silent truncation).
    assert v.excluded_scenarios, "degenerate-truth scenarios must be listed, not silently dropped"
    # Scored and excluded are disjoint and together cover all 13 scenarios.
    assert set(v.scored_scenarios) & set(v.excluded_scenarios) == set()
    assert set(v.scored_scenarios) | set(v.excluded_scenarios) == {f"S{i:02d}" for i in range(1, 14)}


def test_report_is_deterministic() -> None:
    """build_report is byte-identical on re-run and carries the headline content."""
    matrix = run_invariant_matrix()
    recovery = run_rank_recovery()
    v = gate_verdict(matrix, recovery)
    first = build_report(matrix, recovery, v)
    second = build_report(matrix, recovery, v)
    assert first == second
    assert "PASS" in first
    assert "T_SUBJECT" in first  # the attribution example header
    assert "TASK-13" in first    # the Option-B rationale routes accuracy tuning to TASK-13


def test_report_frames_synthetic_as_diagnostic_not_gate() -> None:
    """Post-pivot (TASK-19): the synthetic report must label itself diagnostic, not the gate,
    and point readers at the real-data gate as the headline adjudicator."""
    matrix = run_invariant_matrix()
    recovery = run_rank_recovery()
    report = build_report(matrix, recovery, gate_verdict(matrix, recovery))
    assert "diagnostic" in report.lower()
    assert "real-eval.md" in report


def test_trajectory_scenarios_scored_against_point_in_time_truth() -> None:
    """run_rank_recovery scores S04/S11 against point-in-time truth, not the static key.

    Under the static key S11 bespoke gets Spearman −0.5 (backwards: the model correctly
    ranks the rising team above the falling one, but the static answer key disagrees).
    After wiring in point-in-time truth, S11 bespoke Spearman must be > −0.5 (i.e. no
    longer the backwards score). Static scenarios (e.g. S07, all-flat teams) score
    identically to before — we assert S07 bespoke Spearman stays positive.
    """
    r = run_rank_recovery()

    # S11: with point-in-time truth RISER is correctly ranked above FALLER at end-of-season,
    # so bespoke's current-form call should yield a positive Spearman (not the old ~-0.5).
    s11_bespoke_rho = r["S11"]["bespoke"].spearman_rho
    assert s11_bespoke_rho > 0.0, (
        f"S11 bespoke Spearman should be > 0.0 with point-in-time truth, got {s11_bespoke_rho:.4f}. "
        "Under static key it was ~-0.5 (the trajectory artifact); this confirms the fix landed."
    )

    # S07: all-flat teams → static and point-in-time truth are identical → score is unchanged.
    s07_bespoke_rho = r["S07"]["bespoke"].spearman_rho
    assert s07_bespoke_rho > 0.0, (
        f"S07 bespoke Spearman should remain positive (flat scenario, static truth), "
        f"got {s07_bespoke_rho:.4f}"
    )


def test_gate_verdict_is_computed_not_asserted() -> None:
    """gate_verdict is derived from the recomputed means, not prose-asserted.

    After TASK-14 the trajectory correction may flip the gate to PASS (or keep it FAIL —
    we do not hard-code which). We assert: the boolean equals the mean comparison, and
    that the verdict is consistent with the actual score values.
    """
    matrix = run_invariant_matrix()
    recovery = run_rank_recovery()
    v = gate_verdict(matrix, recovery)

    # The boolean must be consistent with the computed means.
    assert v.bespoke_beats_mhr == (v.mean_spearman["bespoke"] > v.mean_spearman["mhr"]), (
        "bespoke_beats_mhr must equal (mean bespoke > mean mhr), not be hard-coded"
    )
    # Fairness half still holds (model unchanged).
    assert v.bespoke_all_invariants_pass is True
