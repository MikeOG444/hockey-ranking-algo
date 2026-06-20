"""MHR replica benchmark (brief §3.1).

MyHockey Rankings style: per-game goal differential capped at ±7, averaged per team (AGD),
plus the mean of opponents' current ratings (SCHED), iterated to convergence. Centered to
mean 0. No per-game result floor.

This model is a *benchmark* — it is EXPECTED to fail invariants. That failure is the
comparative story: it motivates the bespoke model's structural floor.

Invariants this model FAILS:
  I1 (result ordering): A team that lost vs opponent X can outrate one that won vs X (same
    margin) because season-wide AGD is the only result signal — a blowout win elsewhere
    overwhelms a single-game result. There is no per-game base(result) floor. See
    test_I1_violation_documented for a concrete constructed case.
  I2 (win-monotone): A bigger win against a weak opponent can lower the opponents' SCHED
    and reduce the team's net rating in subsequent iterations — no structural guarantee that
    more margin never hurts. (Note: the ±7 cap produces a non-strict plateau above 7 goals,
    which satisfies I2's non-decreasing condition in isolation, but the structural failure
    above can still invert I2 when SCHED dynamics are involved.)
  I4 (close-loss floor): No structural distinction between a 1-goal loss and a 7-goal loss
    via result category; the only signal is raw capped GD, so deeper losses are always worse.
  I7 (underperformance no-flip): No mechanism to prevent the SCHED term from inverting
    result order when the gap in opponent strength is large enough.

Invariants this model PASSES (on well-connected schedules):
  I8 (determinism): batch solve, no RNG, canonical sort order → byte-identical output.
  I9 (convergence/uniqueness): with lam > 0 and centering the iteration is a strict
    contraction (spectral radius of the coupling matrix is < 1 even on bipartite graphs).
"""

from collections.abc import Iterable, Mapping

from core.game import GameRow
from models.bespoke import RateResult

GD_CAP = 7  # MHR caps each game's raw goal differential at ±7 (brief §3.1)


def rate(
    games: Iterable[GameRow],
    *,
    lam: float = 0.05,
    tol: float = 1e-12,
    max_iter: int = 1000,
    init: Mapping[str, float] | None = None,
) -> RateResult:
    """Solve MHR-style season ratings as the fixed point of:

        r_i  ←  (1 − lam) · (AGD_i + mean_j r_j)

    where AGD_i is team i's average capped goal differential, and mean_j r_j is the mean
    of i's opponents' current ratings (SCHED). Ratings are re-centered to mean 0 each pass.

    `lam` is a small regularization that makes the iteration a strict contraction on any
    schedule graph, including bipartite or sparse ones (without it, a perfectly bipartite
    graph oscillates at eigenvalue −1). The qualitative behaviour — and the I1 violation —
    are unchanged by the regularization; it only ensures convergence.
    """
    games = list(games)
    teams = sorted(set(g.team for g in games) | set(g.opponent for g in games))

    # Pre-compute per-team entries: (capped_gd, opponent_id). Both perspectives per game.
    entries: dict[str, list[tuple[float, str]]] = {t: [] for t in teams}
    for g in games:
        raw_gd = g.goals_team - g.goals_opponent
        capped = float(max(-GD_CAP, min(GD_CAP, raw_gd)))
        entries[g.team].append((capped, g.opponent))
        entries[g.opponent].append((-capped, g.team))

    # Canonical sort so output is byte-identical regardless of input row order (I8).
    for t in teams:
        entries[t].sort(key=lambda e: (e[1], e[0]))

    r: dict[str, float] = {t: 0.0 for t in teams}
    if init is not None:
        r = {t: float(init.get(t, 0.0)) for t in teams}

    for _ in range(max_iter):
        new: dict[str, float] = {}
        for t in teams:
            ent = entries[t]
            if not ent:
                new[t] = 0.0
                continue
            agd = sum(gd for gd, _ in ent) / len(ent)
            sched = sum(r[opp] for _, opp in ent) / len(ent)
            new[t] = (1.0 - lam) * (agd + sched)

        # Re-center to mean 0 (gauge fix; also anchors disconnected pods together).
        mean = sum(new.values()) / len(new)
        for t in teams:
            new[t] -= mean

        delta = max(abs(new[t] - r[t]) for t in teams)
        r = new
        if delta < tol:
            break

    # tiers/per_game_attribution/trend are intentionally empty for this benchmark.
    # MHR has no per-game credit decomposition (no base/marginAdj/scheduleTerm terms), so
    # attribution cannot be populated without misrepresenting the model. The harness must
    # guard on empty per_game_attribution before running I12 checks on this model.
    return RateResult(ratings=r, tiers={}, per_game_attribution={}, trend={})
