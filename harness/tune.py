"""Stage-A parameter sweep — the auditable 'why these values' for the bespoke defaults (TASK-13).

This is a **committed, deterministic artifact**, not a throwaway. The shipped `BespokeParams`
defaults are this sweep's argmax, and a guard test pins that. The sweep:

1. defines a **finite, fixed-order grid** over the three tuning axes (memo §9 ranges), each axis a
   *falsifiable assumption with a named confirming scenario* (memo §11 ethos):
     - ``alpha``         ↔ S07 / I6 (the schedule term must clear the win/loss floor at the
                            solver's *reachable* converged spread ≈ 4.38, so alpha >= 0.7; and the
                            §3 contraction needs alpha < 1);
     - ``rho`` (= rho_tier) ↔ S11 / I11 (recency tracks current form — pushing rho toward 0 would
                            kill the trend feature, which is forbidden, so rho stays in [0.1, 0.4]);
     - ``tier_strength``  ↔ S05 / giant-killer (a single multiplier on the tier table's *distance
                            from neutral*, kept orthogonal to the schedule term — never widen alpha
                            to cover a weak tier table, that double-counts opponent strength, Q3).
2. scores each point by **mean Spearman over exactly the gate's scorable scenarios** (reusing the
   `harness.run`/`harness.metrics` primitives, so the number tuned *is* the number the gate reads);
3. **filters by hard constraints** — the S07/I6 end-to-end check and the contraction bound
   ``alpha*(1-lam) < 1`` — so the score can never buy an invariant-unsafe point;
4. returns the argmax under a **stated, deterministic tie-break** (highest mean Spearman; ties
   broken by smaller alpha, then rho closest to the memo strawman 0.2, then tier-strength closest
   to neutral 1.0 — *prefer the least exotic knob that wins*).

No RNG, no wall-clock, stable iteration order: re-running yields byte-identical results (asserted
by ``harness/test_tune.py::test_sweep_is_deterministic``). ``main()`` prints the full per-point
table — the auditable record of what was tried and why the winner won.

**Honest-fallback (no cherry-picking).** If no feasible point beats the MHR replica on the full
scorable set, the result object still carries the per-scenario residual so the report can diagnose
the gap precisely rather than slice the scenario set until bespoke 'wins'.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from harness.adapters import mhr
from harness.metrics import score_model
from harness.run import (
    SCENARIO_BUILDERS,
    SCORABLE_STD_FLOOR,
    _true_rating_std,
)
from models.bespoke import BespokeParams, rate_weekly
from scenarios.builders import build_s07_close_vs_tier

# --- the grid (small, legible, inside the safe region) ---------------------------------------

# alpha: floor 0.7 (I6 at the reachable gap) … ceiling < 1 (contraction margin). The single most
# important axis — it both fixes I6 end-to-end and moves rank recovery.
ALPHA_GRID: tuple[float, ...] = (0.70, 0.75, 0.80, 0.85, 0.90)
# rho (= rho_tier): the memo §9 range (half-life ~3-4 weeks ⇒ ~0.2). Lower rho scores the
# trajectory scenarios better but weakens current-form tracking — bounded away from 0 to keep I11.
RHO_GRID: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4)
# tier_strength: one multiplier on the tier table's distance from the neutral 1.0 (1.0 = the memo
# table unchanged; 2.0 = doubled spread). Kept a single knob for legibility (criterion 3) and
# orthogonal to alpha. 1.0 documents 'tier table as memo'; >1 documents 'we tried widening it'.
TIER_STRENGTH_GRID: tuple[float, ...] = (1.0, 2.0)

# The model's uniqueness damping (memo §9) — fixed; it sets uniqueness, not accuracy. The
# contraction bound alpha*(1-LAM) < 1 is checked against it.
LAM_DEFAULT: float = 0.05

# The memo §9 strawman anchors used by the tie-break ('closest to the least exotic knob').
_RHO_ANCHOR = 0.2
_TIER_ANCHOR = 1.0


@dataclass(frozen=True)
class GridPoint:
    """One point in the tuning grid — the three axes that move accuracy within the safe region."""

    alpha: float
    rho: float          # also used as rho_tier (memo §9: rho_tier = rho)
    tier_strength: float


@dataclass(frozen=True)
class PointScore:
    """A scored grid point: its mean Spearman over the scorable set and whether it is feasible."""

    point: GridPoint
    mean_spearman: float
    feasible: bool


@dataclass(frozen=True)
class SweepResult:
    """The sweep's verdict — the winner, the full feasible ranking, and the MHR comparison.

    ``residual_by_scenario`` carries (scenario, bespoke_rho, mhr_rho) for the winner over every
    scorable scenario, so the honest-fallback diagnosis (where bespoke still trails and why) is
    representable without re-running the sweep.
    """

    winner: GridPoint
    winner_mean_spearman: float
    mhr_mean_spearman: float
    beats_mhr: bool
    ranking: tuple[PointScore, ...]
    residual_by_scenario: tuple[tuple[str, float, float], ...]


def candidate_params(point: GridPoint) -> BespokeParams:
    """Build the ``BespokeParams`` for a grid point: alpha set, the tier table scaled about its
    neutral 1.0 by ``tier_strength`` (so tier 3 stays exactly 1.0 and every entry stays >= 0 for
    legible multipliers >= 1). The floor (W/T/L, bonus/penalty buckets) is untouched — we move
    constants within the safe region, never the structure."""
    base = BespokeParams()
    s = point.tier_strength

    def scale(table: tuple[float, ...]) -> tuple[float, ...]:
        return tuple(1.0 + s * (x - 1.0) for x in table)

    return replace(
        base,
        alpha=point.alpha,
        tier_m=scale(base.tier_m),
        tier_p=scale(base.tier_p),
        tier_default_m=1.0 + s * (base.tier_default_m - 1.0),
        tier_default_p=1.0 + s * (base.tier_default_p - 1.0),
    )


def candidate_rate(point: GridPoint):
    """A ``(games) -> RateResult`` adapter for a candidate point — the full tier+trend weekly solve
    under its params and rho (threaded through, never hard-forked from the model)."""
    params = candidate_params(point)

    def fn(games):
        return rate_weekly(games, params, rho=point.rho, rho_tier=point.rho)

    return fn


def scorable_scenarios() -> list[str]:
    """Exactly the gate's scorable pool — scenarios whose planted truth has real spread (the same
    set & rule ``gate_verdict`` uses), in S01→S13 order."""
    return [s for s, _ in SCENARIO_BUILDERS if _true_rating_std(s) > SCORABLE_STD_FLOOR]


def _rho_over(scen_ids: list[str], rate_fn) -> dict[str, float]:
    """Spearman rho per scenario for a given rating function (rebuilds each dataset fresh)."""
    builders = dict(SCENARIO_BUILDERS)
    out: dict[str, float] = {}
    for s in scen_ids:
        dataset, _meta = builders[s]()
        out[s] = score_model(dataset.ground_truth, rate_fn(dataset.games)).spearman_rho
    return out


def score_point(point: GridPoint) -> float:
    """Mean Spearman rho for a candidate point over the scorable scenarios (the tuning objective)."""
    rhos = _rho_over(scorable_scenarios(), candidate_rate(point))
    return float(np.mean([rhos[s] for s in scorable_scenarios()])) if rhos else 0.0


def mhr_mean_spearman() -> float:
    """The MHR replica's mean Spearman over the same scorable set — the gate target to beat."""
    rhos = _rho_over(scorable_scenarios(), mhr)
    scen = scorable_scenarios()
    return float(np.mean([rhos[s] for s in scen])) if scen else 0.0


# --- hard constraints (the score can never buy an unsafe point) -------------------------------


def satisfies_i6(point: GridPoint) -> bool:
    """End-to-end I6 at the reachable gap (S07): a 1-goal loss to the elite must out-credit a
    1-goal win over the worst, on the *converged* spread under this candidate's params."""
    params = candidate_params(point)
    dataset, _meta = build_s07_close_vs_tier()
    result = rate_weekly(dataset.games, params, rho=point.rho, rho_tier=point.rho)
    attr = result.per_game_attribution.get("T_SUBJECT", [])
    loss = next((bd for bd in attr if bd.base == 0.0), None)   # the loss to T_TOP
    win = next((bd for bd in attr if bd.base == 3.0), None)    # the win over T_BOTTOM
    if loss is None or win is None:
        return False
    return loss.total > win.total


def satisfies_contraction(point: GridPoint, lam: float = LAM_DEFAULT) -> bool:
    """I9 stays a contraction: the alpha-coupling map contracts iff ``alpha*(1-lam) < 1``."""
    return point.alpha * (1.0 - lam) < 1.0


def is_feasible(point: GridPoint) -> bool:
    """A point is selectable only if it satisfies *both* hard constraints (I6 + contraction)."""
    return satisfies_i6(point) and satisfies_contraction(point)


# --- the sweep ---------------------------------------------------------------------------------


def grid() -> list[GridPoint]:
    """The full finite grid in fixed (alpha, rho, tier_strength) order — deterministic (I8)."""
    return [
        GridPoint(alpha=a, rho=r, tier_strength=t)
        for a in ALPHA_GRID
        for r in RHO_GRID
        for t in TIER_STRENGTH_GRID
    ]


def _tie_break_key(ps: PointScore) -> tuple[float, float, float, float]:
    """Deterministic ordering key: best mean Spearman first; ties broken toward the least exotic
    knob — smaller alpha, then rho nearest the strawman 0.2, then tier-strength nearest neutral 1.0.
    """
    p = ps.point
    return (
        -ps.mean_spearman,                  # higher score first
        p.alpha,                            # then smaller alpha
        abs(p.rho - _RHO_ANCHOR),           # then rho closest to the memo strawman
        abs(p.tier_strength - _TIER_ANCHOR),  # then tier-strength closest to neutral
    )


def rank_points(scored: list[PointScore]) -> list[PointScore]:
    """Rank the *feasible* points best-first under the stated tie-break. Infeasible points are
    dropped from the ranking (they can never be selected)."""
    feasible = [ps for ps in scored if ps.feasible]
    return sorted(feasible, key=_tie_break_key)


def score_grid(points: list[GridPoint] | None = None) -> list[PointScore]:
    """Score + feasibility-check every grid point once, in fixed order — the single place the
    (expensive) per-point evaluation happens, so callers reuse it rather than recompute."""
    points = points if points is not None else grid()
    return [
        PointScore(point=pt, mean_spearman=score_point(pt), feasible=is_feasible(pt))
        for pt in points
    ]


def run_sweep(
    points: list[GridPoint] | None = None,
    scored: list[PointScore] | None = None,
) -> SweepResult:
    """Score and rank every grid point, select the feasible argmax under the tie-break, and attach
    the MHR comparison + the winner's per-scenario residual (for an honest-fallback diagnosis).

    Pass a pre-computed ``scored`` to avoid re-evaluating the grid (``main`` does this so its
    printed table and the verdict share one evaluation)."""
    if scored is None:
        scored = score_grid(points)
    ranking = rank_points(scored)
    if not ranking:
        raise ValueError("No feasible grid point — every candidate failed I6 or the contraction bound.")
    winner = ranking[0].point
    winner_mean = ranking[0].mean_spearman

    mhr_mean = mhr_mean_spearman()
    scen = scorable_scenarios()
    b_rhos = _rho_over(scen, candidate_rate(winner))
    m_rhos = _rho_over(scen, mhr)
    residual = tuple((s, b_rhos[s], m_rhos[s]) for s in scen)

    return SweepResult(
        winner=winner,
        winner_mean_spearman=winner_mean,
        mhr_mean_spearman=mhr_mean,
        beats_mhr=winner_mean > mhr_mean,
        ranking=tuple(ranking),
        residual_by_scenario=residual,
    )


def main() -> None:
    """Print the full sweep: the per-point table (the auditable 'what we tried'), the winner, and
    the MHR comparison with the honest-fallback diagnosis when the gate is not met."""
    scored = score_grid()           # evaluate the grid once …
    result = run_sweep(scored=scored)  # … and reuse it for both the table and the verdict

    print("Stage-A tuning sweep — bespoke parameter grid (TASK-13)\n")
    print(f"{'alpha':>6} {'rho':>5} {'tierS':>6} {'feasible':>9} {'meanRho':>9}")
    for ps in sorted(scored, key=lambda x: (-x.mean_spearman, x.point.alpha)):
        p = ps.point
        print(
            f"{p.alpha:>6.2f} {p.rho:>5.2f} {p.tier_strength:>6.2f} "
            f"{str(ps.feasible):>9} {ps.mean_spearman:>9.4f}"
        )

    w = result.winner
    print(
        f"\nWinner (feasible argmax): alpha={w.alpha:.2f}, rho=rho_tier={w.rho:.2f}, "
        f"tier_strength={w.tier_strength:.2f}"
    )
    print(
        f"Mean Spearman over scorable scenarios — bespoke {result.winner_mean_spearman:.4f} "
        f"vs mhr {result.mhr_mean_spearman:.4f} "
        f"⇒ beats MHR: {result.beats_mhr}"
    )
    if not result.beats_mhr:
        print("\nHonest-fallback — per-scenario residual (bespoke vs mhr):")
        for s, b, m in result.residual_by_scenario:
            flag = "  <-- bespoke trails" if b < m - 1e-9 else ""
            print(f"  {s}: bespoke {b:>7.4f}  mhr {m:>7.4f}{flag}")


if __name__ == "__main__":
    main()
