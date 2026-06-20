"""Ridge Massey benchmark (brief §3.3).

Regularized least-squares on goal margins: for each game between teams i and j with margin m,
the Massey system encodes `rating_i − rating_j ≈ m`. Assembling one equation per game gives an
over-determined linear system whose normal equations reduce to the N×N Massey matrix M:

    M[i][i] = games played by team i
    M[i][j] = −(games between teams i and j)   for i ≠ j
    b[i]    = sum of margins for team i (positive = goals scored, negative = goals allowed)

M is always singular (row sums equal zero — the rating gauge is undefined). A ridge (L2) penalty
λI is added so the system becomes (M + λI)r = b, which is always positive definite and therefore
has a unique solution regardless of schedule connectivity (disconnected pods included). The result
is then centered to mean 0 for gauge consistency with the other models.

This model is a *benchmark* — it is expected to fail fairness invariants (I1, I4, I6, I7) because
it has no per-game result floor. Margins are the only signal; a team that wins every game by 1
goal can rate below one that lost big and won bigger.

Invariants this model PASSES:
  I8  — determinism: direct solve (no RNG, no iteration), canonical team sort → byte-identical.
  I9  — uniqueness: ridge term makes (M + λI) positive definite → unique finite solution on any
        schedule graph including disconnected ones.

numpy is sufficient; scipy is not required.
"""

from collections.abc import Iterable

import numpy as np

from core.game import GameRow
from models.bespoke import RateResult

# Default ridge strength. Small enough not to distort ratings on dense schedules, large enough
# to stabilise completely disconnected pods. 0.1 goals² of regularization is imperceptible on a
# 10+ game season but prevents the Massey matrix's null-space from causing numerical blow-up.
DEFAULT_RIDGE = 0.1


def rate(
    games: Iterable[GameRow],
    *,
    margin_cap: int | None = None,
    ridge: float = DEFAULT_RIDGE,
) -> RateResult:
    """Compute Ridge Massey ratings from a list of Level-0 game rows.

    Args:
        games:      Iterable of GameRow (Level-0 observed records only).
        margin_cap: If set, each game's goal-difference is clamped to ±margin_cap before
                    entering the Massey system. None (default) means no cap.
        ridge:      L2 regularization strength added to the diagonal of the Massey matrix.
                    Must be > 0 to guarantee a unique solution. Default 0.1.

    Returns:
        RateResult with ratings centered to mean 0. tiers, per_game_attribution, and trend
        are left empty — this is a benchmark with no decomposition or tier logic.
    """
    games = list(games)
    # Deterministic team ordering (I8) — same canonical sort as bespoke/MHR.
    teams = sorted(set(g.team for g in games) | set(g.opponent for g in games))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    M = np.zeros((n, n), dtype=np.float64)
    b = np.zeros(n, dtype=np.float64)

    for g in games:
        raw_margin = float(g.goals_team - g.goals_opponent)
        if margin_cap is not None:
            raw_margin = max(-float(margin_cap), min(float(margin_cap), raw_margin))

        i, j = idx[g.team], idx[g.opponent]

        # Team i perspective: rating_i - rating_j ≈ raw_margin
        M[i, i] += 1.0
        M[i, j] -= 1.0
        b[i] += raw_margin

        # Team j perspective: rating_j - rating_i ≈ -raw_margin
        M[j, j] += 1.0
        M[j, i] -= 1.0
        b[j] -= raw_margin

    # Ridge: add λI to make the system positive definite on any schedule graph.
    M_reg = M + ridge * np.eye(n, dtype=np.float64)

    r_vec = np.linalg.solve(M_reg, b)

    # Center to mean 0 (gauge fix — same convention as bespoke and MHR).
    r_vec -= r_vec.mean()

    ratings = {t: float(r_vec[idx[t]]) for t in teams}

    # Benchmark: no tier derivation, no per-game attribution, no trend.
    return RateResult(ratings=ratings, tiers={}, per_game_attribution={}, trend={})
