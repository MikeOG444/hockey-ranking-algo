"""Unit + end-to-end tests for harness/metrics.py (TASK-10).

All inputs are constructed inline — no fixtures needed. Each test exercises one
metric independently, then one end-to-end call through score_model.
"""

import math

from harness.metrics import (
    centered_rmse,
    score_model,
    spearman_rho,
    tier_accuracy,
)


# ---------------------------------------------------------------------------
# Spearman ρ unit tests
# ---------------------------------------------------------------------------


def test_spearman_perfect():
    # Same rank order, different magnitudes → ρ == 1.0
    true_r = {"A": 3.0, "B": 2.0, "C": 1.0}
    model_r = {"A": 9.0, "B": 5.0, "C": 1.0}
    rho = spearman_rho(true_r, model_r)
    assert abs(rho - 1.0) < 1e-9, f"Expected ρ=1.0, got {rho}"


def test_spearman_inverse():
    # Reversed rank order → ρ == -1.0
    true_r = {"A": 3.0, "B": 2.0, "C": 1.0}
    model_r = {"A": 1.0, "B": 2.0, "C": 3.0}
    rho = spearman_rho(true_r, model_r)
    assert abs(rho - (-1.0)) < 1e-9, f"Expected ρ=-1.0, got {rho}"


def test_spearman_partial():
    # 5 teams; model swaps the two bottom teams (D↔E) → ρ == 0.9 > 0.8
    true_r = {"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "E": 1.0}
    model_r = {"A": 5.0, "B": 4.0, "C": 3.0, "D": 1.0, "E": 2.0}
    rho = spearman_rho(true_r, model_r)
    assert rho > 0.8, f"Expected ρ > 0.8 for near-perfect ordering, got {rho}"


# ---------------------------------------------------------------------------
# Centered RMSE unit tests
# ---------------------------------------------------------------------------


def test_centered_rmse_zero_after_shift():
    # Same shape, shifted by +2 → centering removes the shift → RMSE == 0
    true_r = {"A": 0.5, "B": -0.5}
    model_r = {"A": 2.5, "B": 1.5}
    rmse = centered_rmse(true_r, model_r)
    assert abs(rmse) < 1e-9, f"Expected RMSE=0 after centering, got {rmse}"


def test_centered_rmse_compressed_signal():
    # true = [1, 0, -1], model = [0.5, 0, -0.5] (compressed by 0.5×)
    # Both vectors already have mean 0; centered diffs = [0.5, 0, -0.5]
    # RMSE = sqrt(mean([0.25, 0.0, 0.25])) = sqrt(1/6) ≈ 0.40825
    true_r = {"A": 1.0, "B": 0.0, "C": -1.0}
    model_r = {"A": 0.5, "B": 0.0, "C": -0.5}
    expected = math.sqrt((0.25 + 0.0 + 0.25) / 3)  # sqrt(1/6) ≈ 0.40825
    rmse = centered_rmse(true_r, model_r)
    assert abs(rmse - expected) < 1e-9, f"Expected RMSE={expected}, got {rmse}"


# ---------------------------------------------------------------------------
# Tier accuracy unit tests
# ---------------------------------------------------------------------------


def test_tier_accuracy_perfect_matching_labels():
    # Identical assignments → 1.0
    true_t = {"A": 1, "B": 1, "C": 2, "D": 2}
    model_t = {"A": 1, "B": 1, "C": 2, "D": 2}
    acc = tier_accuracy(true_t, model_t)
    assert abs(acc - 1.0) < 1e-9, f"Expected tier_accuracy=1.0, got {acc}"


def test_tier_accuracy_relabeled_flip():
    # Tier labels 1↔2 are swapped → best permutation maps them back → 1.0
    true_t = {"A": 1, "B": 1, "C": 2, "D": 2}
    model_t = {"A": 2, "B": 2, "C": 1, "D": 1}
    acc = tier_accuracy(true_t, model_t)
    assert abs(acc - 1.0) < 1e-9, f"Expected tier_accuracy=1.0 under best permutation, got {acc}"


def test_tier_accuracy_partial():
    # 4 teams; team B is mislabelled → 3/4 correct under identity permutation
    true_t = {"A": 1, "B": 1, "C": 2, "D": 2}
    model_t = {"A": 1, "B": 2, "C": 2, "D": 2}
    acc = tier_accuracy(true_t, model_t)
    assert abs(acc - 0.75) < 1e-9, f"Expected tier_accuracy=0.75, got {acc}"


def test_no_true_tiers_returns_zero():
    # Ground truth with all tier=None → tier_accuracy=0.0, n_tiers_scored=0
    from generator.simulate import TeamParams
    from models.bespoke import RateResult

    ground_truth = [
        TeamParams(id="A", attack=0.5, defense=0.0, tier=None),
        TeamParams(id="B", attack=0.0, defense=0.5, tier=None),
    ]
    # Minimal RateResult: A and B have ratings, no tiers
    result = RateResult(
        ratings={"A": 1.0, "B": -1.0},
        tiers={"A": 1, "B": 2},  # model has tiers, but true tiers are None
        per_game_attribution={},
        trend={},
        center_offset=0.0,
    )
    mr = score_model(ground_truth, result)
    assert mr.tier_accuracy == 0.0, f"Expected tier_accuracy=0.0 when true tiers all None, got {mr.tier_accuracy}"
    assert mr.n_tiers_scored == 0, f"Expected n_tiers_scored=0, got {mr.n_tiers_scored}"


# ---------------------------------------------------------------------------
# End-to-end integration test through score_model
# ---------------------------------------------------------------------------


def test_score_model_end_to_end():
    """6-team synthetic world; flat solve; assert n_teams and directional Spearman."""
    from generator.simulate import Matchup, TeamParams, WorldConfig, simulate
    import models.bespoke as bespoke

    teams = [
        TeamParams(id="S1", attack=1.5, defense=0.5, tier=1),
        TeamParams(id="S2", attack=1.5, defense=0.5, tier=1),
        TeamParams(id="S3", attack=1.5, defense=0.5, tier=1),
        TeamParams(id="W1", attack=0.5, defense=1.5, tier=2),
        TeamParams(id="W2", attack=0.5, defense=1.5, tier=2),
        TeamParams(id="W3", attack=0.5, defense=1.5, tier=2),
    ]
    team_ids = [t.id for t in teams]
    matchups = [
        Matchup(week=week, team=a, opponent=b)
        for week in range(1, 5)
        for i, a in enumerate(team_ids)
        for b in team_ids[i + 1 :]
    ]
    config = WorldConfig(teams=teams, schedule=matchups, seed=42)
    dataset = simulate(config)

    result = bespoke.rate(dataset.games)
    mr = score_model(dataset.ground_truth, result)

    assert mr.n_teams == 6, f"Expected n_teams=6, got {mr.n_teams}"
    assert mr.spearman_rho > 0.7, (
        f"Expected spearman_rho > 0.7 (strong-vs-weak ordering), got {mr.spearman_rho:.4f}"
    )
    # Flat rate() emits empty tiers → no tier scoring
    assert mr.n_tiers_scored == 0, f"Expected n_tiers_scored=0 for flat solve, got {mr.n_tiers_scored}"
