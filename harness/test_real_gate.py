"""Tests for harness.real_gate — written first (TDD).

The real-data evaluation gate is the project's headline adjudicator (the pivot of
2026-06-24): score every model against signal we actually have from the real MHR
season — head-to-head gauntlet agreement (who-actually-beat-whom) and agreement
with the published MHR rank order — instead of synthetic rank-recovery.

All tests are deterministic: no RNG, no wall-clock, same input → same output.
The pure-scoring and gate-verdict logic is exercised with hand-built rankings so
the assertions don't depend on any real model's exact output; real-model wiring is
checked only for structure and byte-identical determinism.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Pure scoring — model ranking vs the two real-data yardsticks
# ---------------------------------------------------------------------------

GAUNTLET = ["A", "B", "C", "D"]      # best-first head-to-head gauntlet order
MHR_ORDER = ["A", "C", "B", "D"]     # best-first published MHR order


def test_score_ranking_perfect_gauntlet():
    """A ranking identical to the gauntlet scores ρ = 1.0 on the gauntlet axis."""
    from harness.real_gate import score_ranking

    g_rho, _ = score_ranking(GAUNTLET, GAUNTLET, MHR_ORDER)
    assert g_rho == pytest.approx(1.0)


def test_score_ranking_perfect_published():
    """A ranking identical to the published MHR order scores ρ = 1.0 on the MHR axis."""
    from harness.real_gate import score_ranking

    _, m_rho = score_ranking(MHR_ORDER, GAUNTLET, MHR_ORDER)
    assert m_rho == pytest.approx(1.0)


def test_score_ranking_reversed_is_negative_one():
    """A fully reversed ranking scores ρ = -1.0 against the gauntlet."""
    from harness.real_gate import score_ranking

    g_rho, _ = score_ranking(list(reversed(GAUNTLET)), GAUNTLET, MHR_ORDER)
    assert g_rho == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# Gate verdict — bespoke vs the MHR replica on the headline (gauntlet) axis
# ---------------------------------------------------------------------------


def _score(name, gauntlet_rho, mhr_rho):
    from harness.real_gate import ModelScore

    return ModelScore(name=name, gauntlet_rho=gauntlet_rho, mhr_rho=mhr_rho)


def test_gate_passes_when_bespoke_leads_on_gauntlet():
    """Gate PASSES when bespoke's gauntlet agreement is at least the MHR replica's."""
    from harness.real_gate import gate_verdict

    scores = [
        _score("bespoke", 0.84, 0.70),
        _score("mhr_replica", 0.83, 0.99),
        _score("ridge_massey", 0.50, 0.40),
    ]
    verdict = gate_verdict(scores)
    assert verdict["passed"] is True
    assert verdict["margin"] == pytest.approx(0.01)


def test_gate_fails_when_mhr_replica_leads_on_gauntlet():
    """Gate FAILS honestly when the MHR replica out-agrees bespoke on the gauntlet."""
    from harness.real_gate import gate_verdict

    scores = [
        _score("bespoke", 0.80, 0.70),
        _score("mhr_replica", 0.83, 0.99),
        _score("ridge_massey", 0.50, 0.40),
    ]
    verdict = gate_verdict(scores)
    assert verdict["passed"] is False
    assert verdict["margin"] == pytest.approx(-0.03)


# ---------------------------------------------------------------------------
# Report builder — deterministic markdown
# ---------------------------------------------------------------------------


def _sample_scores():
    return [
        _score("bespoke", 0.8351, 0.7000),
        _score("mhr_replica", 0.8296, 0.9900),
        _score("ridge_massey", 0.5000, 0.4000),
    ]


def test_report_is_deterministic():
    """build_report is a pure function of its inputs → byte-identical on re-run (I8)."""
    from harness.real_gate import build_report, gate_verdict

    scores = _sample_scores()
    verdict = gate_verdict(scores)
    a = build_report(scores, verdict, n_games=2130, n_ranked=50)
    b = build_report(scores, verdict, n_games=2130, n_ranked=50)
    assert a == b


def test_report_lists_all_three_models_and_both_axes():
    """Headline table names every model and both real-data agreement axes."""
    from harness.real_gate import build_report, gate_verdict

    scores = _sample_scores()
    report = build_report(scores, gate_verdict(scores), n_games=2130, n_ranked=50)
    for name in ("bespoke", "mhr_replica", "ridge_massey"):
        assert name in report
    assert "Gauntlet" in report
    assert "MHR" in report


def test_report_marks_synthetic_as_diagnostic_not_gate():
    """The report explicitly demotes the synthetic suite to diagnostic, not the gate."""
    from harness.real_gate import build_report, gate_verdict

    scores = _sample_scores()
    report = build_report(scores, gate_verdict(scores), n_games=2130, n_ranked=50)
    assert "diagnostic" in report.lower()


def test_report_states_verdict():
    """The verdict (PASS/FAIL) appears verbatim in the report so the gate reads honestly."""
    from harness.real_gate import build_report, gate_verdict

    scores = _sample_scores()  # bespoke leads → PASS
    report = build_report(scores, gate_verdict(scores), n_games=2130, n_ranked=50)
    assert "PASS" in report


# ---------------------------------------------------------------------------
# Real-model wiring — structure + determinism on the actual MHR dataset
# ---------------------------------------------------------------------------


def test_evaluate_returns_canonical_three_models():
    """evaluate_models runs the real dataset and returns bespoke/mhr_replica/ridge in order."""
    from harness.real_gate import evaluate_models, load_real_inputs

    games, mhr_order, ranked_set = load_real_inputs()
    scores = evaluate_models(games, mhr_order, ranked_set)
    assert [s.name for s in scores] == ["bespoke", "mhr_replica", "ridge_massey"]
    for s in scores:
        assert -1.0 <= s.gauntlet_rho <= 1.0
        assert -1.0 <= s.mhr_rho <= 1.0


def test_evaluate_is_deterministic_on_real_data():
    """Two independent evaluations of the real dataset are byte-identical (I8)."""
    from harness.real_gate import evaluate_models, load_real_inputs

    games, mhr_order, ranked_set = load_real_inputs()
    a = evaluate_models(games, mhr_order, ranked_set)
    b = evaluate_models(games, mhr_order, ranked_set)
    assert a == b
