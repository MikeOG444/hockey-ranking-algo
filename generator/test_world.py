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

from generator.world import draw_scoreline, expected_goals


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
