"""Synthetic world model (brief §6): a Poisson / Dixon-Coles goal generator.

Deliberately NOT any candidate rater's own assumptions — generating from Dixon-Coles forces
the margin/schedule methods to recover truth from data not built in their image (avoids circular
validation). There is no home-ice term: the two teams are peers.

Sign convention (so the brief's `rating = attack - defense` holds):
  attack  = scoring strength      (higher -> you score more)
  defense = defensive *weakness*  (higher -> you concede more)
"""

import math

import numpy as np


def expected_goals(attack_scorer: float, defense_conceder: float, mu: float) -> float:
    """Poisson rate (lambda) for the scoring team.

    lambda = exp(mu + attack_scorer + defense_conceder), where mu sets the league baseline
    scoring level (e.g. mu = ln 3 -> ~3 expected goals between neutral teams).
    """
    return math.exp(mu + attack_scorer + defense_conceder)


def draw_scoreline(
    rng: np.random.Generator, lam_team: float, lam_opp: float
) -> tuple[int, int]:
    """Draw one game's (goals_team, goals_opponent) as independent Poisson counts.

    Independent Poisson is the Dixon-Coles model with the low-score correlation term set to
    zero; the correlation correction is a later, optional refinement. The draw consumes the
    given RNG, so reproducibility is the caller's to control via the seed (I8).
    """
    g_team = int(rng.poisson(lam_team))
    g_opp = int(rng.poisson(lam_opp))
    return g_team, g_opp
