"""Synthetic world-model tests (brief §6): Poisson / Dixon-Coles.

Sign convention (so the brief's `rating = attack - defense` holds):
  attack  = scoring strength      (higher -> you score more)
  defense = defensive *weakness*  (higher -> you concede more)
A team's expected goals depend on its own attack and the opponent's defensive weakness:
  lambda = exp(mu + attack_scorer + defense_conceder)
"""

import math

import numpy as np
import pytest

from generator.world import draw_scoreline, draw_scoreline_dc, expected_goals


def test_baseline_rate_is_exp_mu():
    """With neutral teams (attack=defense=0), expected goals = exp(mu)."""
    mu = math.log(3.0)
    assert expected_goals(attack_scorer=0.0, defense_conceder=0.0, mu=mu) == pytest.approx(3.0)


def test_exact_formula():
    mu = math.log(3.0)
    lam = expected_goals(attack_scorer=0.4, defense_conceder=0.2, mu=mu)
    assert lam == math.exp(mu + 0.4 + 0.2)


def test_stronger_attacker_scores_more():
    mu = math.log(3.0)
    weak = expected_goals(attack_scorer=0.1, defense_conceder=0.0, mu=mu)
    strong = expected_goals(attack_scorer=0.9, defense_conceder=0.0, mu=mu)
    assert strong > weak


def test_weaker_defense_concedes_more():
    """A higher opponent defensive weakness means you (the scorer) score more."""
    mu = math.log(3.0)
    vs_tight = expected_goals(attack_scorer=0.0, defense_conceder=0.0, mu=mu)
    vs_leaky = expected_goals(attack_scorer=0.0, defense_conceder=0.5, mu=mu)
    assert vs_leaky > vs_tight


# --- scoreline draws -------------------------------------------------------

def test_same_seed_gives_identical_scoreline():
    """Determinism at the source (I8): identical seed -> byte-identical goals."""
    a = draw_scoreline(np.random.default_rng(42), lam_team=3.0, lam_opp=2.0)
    b = draw_scoreline(np.random.default_rng(42), lam_team=3.0, lam_opp=2.0)
    assert a == b


def test_different_seeds_can_differ():
    """Sanity: the draw actually depends on the RNG, not a constant."""
    rng = np.random.default_rng(1)
    draws = {draw_scoreline(rng, lam_team=3.0, lam_opp=3.0) for _ in range(50)}
    assert len(draws) > 1


def test_scoreline_is_nonnegative_integers():
    g_team, g_opp = draw_scoreline(np.random.default_rng(0), lam_team=2.5, lam_opp=1.5)
    assert isinstance(g_team, int) and isinstance(g_opp, int)
    assert g_team >= 0 and g_opp >= 0


def test_empirical_mean_recovers_lambda():
    """Over many draws each side's mean goals converges to its Poisson rate."""
    rng = np.random.default_rng(7)
    n = 20000
    team_goals = np.empty(n)
    opp_goals = np.empty(n)
    for i in range(n):
        team_goals[i], opp_goals[i] = draw_scoreline(rng, lam_team=2.5, lam_opp=1.5)
    assert team_goals.mean() == pytest.approx(2.5, abs=0.05)
    assert opp_goals.mean() == pytest.approx(1.5, abs=0.05)


# --- Dixon-Coles low-score correction tests --------------------------------


def test_rho_zero_is_identical_to_current():
    """Regression guard (TASK-08): rho=0 must produce byte-identical draws to draw_scoreline.

    The correction vanishes at rho=0 (tau=1 for all low-score pairs), so draw_scoreline_dc
    must call the same underlying Poisson draws in the same order as draw_scoreline.
    """
    n = 500
    seed = 99
    old_draws = [
        draw_scoreline(np.random.default_rng(seed + i), lam_team=3.0, lam_opp=2.0)
        for i in range(n)
    ]
    new_draws = [
        draw_scoreline_dc(np.random.default_rng(seed + i), lam_team=3.0, lam_opp=2.0, rho=0.0)
        for i in range(n)
    ]
    assert old_draws == new_draws, "rho=0 path must be byte-identical to draw_scoreline"


def test_correction_reduces_zero_zero_frequency():
    """DC correction with rho=0.08 must suppress 0-0 draws below independent-Poisson expectation.

    For neutral teams at lambda=3 each, independent Poisson gives P(0-0) = exp(-6) ≈ 0.00248.
    The correction (rho > 0) reduces tau(0,0) = 1 - lambda1*lambda2*rho < 1, so (0,0) pairs
    are rejected more often and the empirical frequency must fall clearly below exp(-6).
    We require the empirical frequency < 0.9 * P_indep (i.e. at least 10% reduction).
    """
    import math

    rho = 0.08
    lam = 3.0
    n = 50_000
    rng = np.random.default_rng(2024)
    zero_zero = sum(
        1
        for _ in range(n)
        if draw_scoreline_dc(rng, lam_team=lam, lam_opp=lam, rho=rho) == (0, 0)
    )
    empirical_freq = zero_zero / n
    p_indep = math.exp(-2 * lam)  # exp(-6) ≈ 0.00248
    assert empirical_freq < 0.9 * p_indep, (
        f"Expected 0-0 frequency below {0.9 * p_indep:.5f} with rho={rho}; "
        f"got {empirical_freq:.5f} ({zero_zero} in {n} draws)"
    )


def test_correction_deterministic():
    """Same seed + same rho → byte-identical draw sequence (I8 determinism)."""
    n = 1_000
    seed = 42
    a = [
        draw_scoreline_dc(np.random.default_rng(seed + i), lam_team=3.0, lam_opp=3.0, rho=0.08)
        for i in range(n)
    ]
    b = [
        draw_scoreline_dc(np.random.default_rng(seed + i), lam_team=3.0, lam_opp=3.0, rho=0.08)
        for i in range(n)
    ]
    assert a == b, "draw_scoreline_dc must be deterministic given the same seed"


def test_invalid_rho_raises():
    """Out-of-range rho must raise ValueError.

    Valid range: 0 <= rho < 1/(lam_team * lam_opp). For lam=3: upper bound ≈ 0.111.
    Negative rho and rho at/above the upper bound are both invalid.
    """
    rng = np.random.default_rng(0)
    lam = 3.0

    # Negative rho is always invalid.
    with pytest.raises(ValueError, match="rho"):
        draw_scoreline_dc(rng, lam_team=lam, lam_opp=lam, rho=-0.01)

    # rho exactly at the upper bound makes tau(0,0) = 0, which is degenerate.
    upper = 1.0 / (lam * lam)
    with pytest.raises(ValueError, match="rho"):
        draw_scoreline_dc(rng, lam_team=lam, lam_opp=lam, rho=upper)
