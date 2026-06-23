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

# Maximum rejection-sampling attempts before we give up (guards against invalid rho values
# that would otherwise spin forever).
_MAX_RETRIES = 100


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


def _tau(g_team: int, g_opp: int, lam_team: float, lam_opp: float, rho: float) -> float:
    """Dixon-Coles correction factor for the four low-score cells (paper eq. 4).

    tau(x, y) is 1 for all (x, y) outside the low-score region {(0,0),(1,0),(0,1),(1,1)}.
    For the four low-score pairs:
        tau(0, 0) = 1 - lam_team * lam_opp * rho   (pair loses mass when rho > 0)
        tau(1, 0) = 1 + lam_opp * rho               (pair gains mass when rho > 0)
        tau(0, 1) = 1 + lam_team * rho              (pair gains mass when rho > 0)
        tau(1, 1) = 1 - rho                          (pair loses mass when rho > 0)
    At rho=0, all tau values are exactly 1 — recovering independent Poisson.
    """
    if g_team == 0 and g_opp == 0:
        return 1.0 - lam_team * lam_opp * rho
    if g_team == 1 and g_opp == 0:
        return 1.0 + lam_opp * rho
    if g_team == 0 and g_opp == 1:
        return 1.0 + lam_team * rho
    if g_team == 1 and g_opp == 1:
        return 1.0 - rho
    return 1.0  # all other scorelines are unaffected by the correction


def draw_scoreline_dc(
    rng: np.random.Generator,
    lam_team: float,
    lam_opp: float,
    rho: float = 0.0,
) -> tuple[int, int]:
    """Draw one game's scoreline using the Dixon-Coles low-score correction (TASK-08).

    At rho=0 this is byte-identical to draw_scoreline — the tau factors are all 1, so every
    candidate draw is accepted on the first try using exactly the same RNG calls.

    For rho > 0, rejection sampling is applied only to the four low-score pairs
    {(0,0), (1,0), (0,1), (1,1)}.  All other scorelines are accepted immediately.

    Valid range: 0 <= rho < 1/(lam_team * lam_opp).  The upper bound keeps tau(0,0) > 0.
    Raises ValueError for out-of-range rho; raises RuntimeError if the retry budget is
    exhausted (which should only happen if rho is barely below the upper bound).

    Determinism (I8): same rng state + same rho -> same output, guaranteed by the
    rejection-sampling loop consuming draws in a fixed, RNG-state-driven order.
    """
    # --- validate rho ----------------------------------------------------------
    if rho < 0.0:
        raise ValueError(
            f"rho must be >= 0 (got {rho}); negative rho is not a valid correction strength."
        )
    upper = 1.0 / (lam_team * lam_opp)
    if rho >= upper:
        raise ValueError(
            f"rho={rho} violates tau(0,0) > 0: must be < 1/(lam_team * lam_opp) = {upper:.6f}."
        )

    # --- rejection-sampling loop -----------------------------------------------
    # When rho=0, tau is 1 everywhere, so the first draw is always accepted and the
    # rng.uniform() call is never reached — byte-identical to draw_scoreline.
    for _ in range(_MAX_RETRIES):
        g_team = int(rng.poisson(lam_team))
        g_opp = int(rng.poisson(lam_opp))

        # Scorelines outside the low-score region are always accepted.
        if g_team > 1 or g_opp > 1:
            return g_team, g_opp

        t = _tau(g_team, g_opp, lam_team, lam_opp, rho)

        # tau >= 1 means the pair gains mass: accept unconditionally (never draw uniform).
        # tau < 1 means the pair loses mass: accept with probability tau.
        if t >= 1.0 or rng.uniform() < t:
            return g_team, g_opp

    raise RuntimeError(
        f"draw_scoreline_dc: failed to accept a scoreline after {_MAX_RETRIES} attempts "
        f"(lam_team={lam_team}, lam_opp={lam_opp}, rho={rho}). "
        "This should not happen for valid rho in [0, 1/(lam_team*lam_opp))."
    )
