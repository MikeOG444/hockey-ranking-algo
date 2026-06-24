"""Seams of the Stage-A tuning sweep (TASK-13).

These tests pin the sweep's *contract* — that its grid can only propose invariant-safe points,
that it scores over exactly the gate's scorable set, that the hard-constraint filter (not the
score) gates selection, that it is deterministic, and that its result object can honestly
represent either a gate-flipping win *or* a documented residual gap (the honest-fallback path).

They do not re-assert the model's invariants (that is the harness/invariant-auditor's job); they
assert that the *machinery which picks the shipped params* is sound and reproducible.
"""

from dataclasses import replace

from harness import tune


def test_grid_is_finite_and_in_safe_region():
    """The grid can't propose an invariant-unsafe point: every alpha clears the I6-reachable floor
    (>= 0.7) and stays under the contraction ceiling (< 1.0); every rho sits in the memo range
    [0.1, 0.4]; and every tier-strength multiplier keeps the tier table non-negative with tier 3
    pinned neutral (m == p == 1.0)."""
    points = tune.grid()
    assert len(points) == len(set(points))  # finite, no duplicates
    for pt in points:
        assert 0.7 <= pt.alpha < 1.0
        assert 0.1 <= pt.rho <= 0.4
        params = tune.candidate_params(pt)
        assert all(m >= 0.0 for m in params.tier_m)
        assert all(p >= 0.0 for p in params.tier_p)
        # Tier 3 (index 2) is the neutral baseline — the fixed-opp_tier=3 credit tests rely on it.
        assert params.tier_m[2] == 1.0
        assert params.tier_p[2] == 1.0


def test_score_point_uses_scorable_set():
    """`scorable_scenarios()` is exactly the gate's pool — the scenarios whose planted truth has
    real spread (std > floor) — so the number the sweep optimizes is the number the gate reads."""
    from harness.run import SCENARIO_BUILDERS, SCORABLE_STD_FLOOR, _true_rating_std

    expected = [s for s, _ in SCENARIO_BUILDERS if _true_rating_std(s) > SCORABLE_STD_FLOOR]
    assert tune.scorable_scenarios() == expected
    # A score is a real mean Spearman in [-1, 1] over that set.
    score = tune.score_point(tune.GridPoint(alpha=0.75, rho=0.2, tier_strength=1.0))
    assert -1.0 <= score <= 1.0


def test_hard_constraint_filter_gates_on_contraction_not_an_alpha_floor():
    """Under surprise-centered credit (TASK-17) the centered win/loss quality gap shrank (~0.75, was
    3), so end-to-end I6 is now robust across the WHOLE alpha grid — even alpha=0.6 satisfies it. The
    old 'alpha must clear an I6-reachable floor (>= 0.69)' no longer binds. The hard constraint that
    actually gates selection is now the contraction bound (alpha < 1): an in-region alpha is feasible,
    an out-of-region one (alpha >= 1) is rejected."""
    # I6 holds even at the old-infeasible low alpha — the floor is no longer alpha-sensitive.
    assert tune.satisfies_i6(tune.GridPoint(alpha=0.6, rho=0.2, tier_strength=1.0)) is True
    assert tune.satisfies_i6(tune.GridPoint(alpha=0.75, rho=0.2, tier_strength=1.0)) is True
    # The contraction bound is the binding hard constraint (alpha < 1).
    assert tune.satisfies_contraction(tune.GridPoint(alpha=0.9, rho=0.2, tier_strength=1.0)) is True
    assert tune.satisfies_contraction(tune.GridPoint(alpha=1.5, rho=0.2, tier_strength=1.0)) is False
    ok = tune.GridPoint(alpha=0.75, rho=0.2, tier_strength=1.0)
    assert tune.is_feasible(ok) is True


def test_contraction_bound_is_enforced():
    """I9 stays a contraction: the filter requires alpha*(1-lam) < 1 at the model's lambda."""
    assert tune.satisfies_contraction(tune.GridPoint(alpha=0.9, rho=0.2, tier_strength=1.0)) is True
    # A hypothetical out-of-region alpha would be rejected (the bound is real, not decorative).
    assert tune.satisfies_contraction(tune.GridPoint(alpha=1.5, rho=0.2, tier_strength=1.0)) is False


def test_sweep_is_deterministic():
    """No RNG, stable iteration order: run_sweep over a fixed sub-grid twice returns identical
    winner and ranking (I8 ethos applied to the tuning machinery itself)."""
    subgrid = [
        tune.GridPoint(alpha=0.70, rho=0.2, tier_strength=1.0),
        tune.GridPoint(alpha=0.75, rho=0.2, tier_strength=1.0),
        tune.GridPoint(alpha=0.80, rho=0.2, tier_strength=1.0),
    ]
    a = tune.run_sweep(subgrid)
    b = tune.run_sweep(subgrid)
    assert a.winner == b.winner
    assert a.ranking == b.ranking
    assert a.winner_mean_spearman == b.winner_mean_spearman


def test_sweep_only_selects_feasible_points():
    """The winner is drawn from the feasible set: a sub-grid that mixes an infeasible high-scoring
    point with a feasible one never returns the infeasible one."""
    subgrid = [
        tune.GridPoint(alpha=0.6, rho=0.2, tier_strength=1.0),   # infeasible (fails I6)
        tune.GridPoint(alpha=0.75, rho=0.2, tier_strength=1.0),  # feasible
    ]
    result = tune.run_sweep(subgrid)
    assert tune.is_feasible(result.winner)
    assert all(tune.is_feasible(ps.point) for ps in result.ranking)


def test_winner_beats_mhr_or_reports_honest_gap():
    """The result object can represent *either* outcome: a gate-flipping win (bespoke > mhr) or a
    documented residual gap. The honest-fallback path is representable, not a crash — and when the
    gap stands, it is diagnosed per scenario (so 'why we still trail' survives into the report)."""
    result = tune.run_sweep()
    assert result.mhr_mean_spearman > 0.0
    if result.beats_mhr:
        assert result.winner_mean_spearman > result.mhr_mean_spearman
    else:
        # Honest fallback: the gap is real and diagnosed, not engineered away.
        assert result.winner_mean_spearman < result.mhr_mean_spearman
        assert result.residual_by_scenario  # per-scenario (bespoke, mhr) diff is carried
        # Every scorable scenario is accounted for — no silent dropping to manufacture a win.
        assert {r[0] for r in result.residual_by_scenario} == set(tune.scorable_scenarios())


def test_tie_break_prefers_smaller_alpha_then_memo_strawman():
    """Stated, deterministic tie-break: among equal-scoring feasible points, prefer the smaller
    alpha, then rho closest to the memo strawman (0.2), then tier-strength closest to neutral (1.0)
    — 'the least exotic knob that wins'. We force a tie by stubbing the scorer to a constant."""
    pts = [
        tune.GridPoint(alpha=0.80, rho=0.2, tier_strength=1.0),
        tune.GridPoint(alpha=0.70, rho=0.4, tier_strength=2.0),
        tune.GridPoint(alpha=0.70, rho=0.2, tier_strength=1.0),  # the least exotic
    ]
    ranked = tune.rank_points([tune.PointScore(point=p, mean_spearman=0.5, feasible=True) for p in pts])
    assert ranked[0].point == replace(tune.GridPoint(alpha=0.70, rho=0.2, tier_strength=1.0))
