"""Scenario 11 — Momentum (I11).

RISER uses trajectory="rising" (attack grows +0.05/week beyond week 1).
FALLER uses trajectory="falling" (attack shrinks -0.05/week beyond week 1).
FIELD×3 are flat baseline teams.

Season-average true ratings are symmetric: RISER starts weak and ends strong; FALLER starts
strong and ends weak; their average strength over the season is approximately equal.

Recency weighting surfaces current form in the point-in-time ratings, and the OLS trend slope
captures the direction of movement.

Asserts:
- trend["RISER"] > 0 > trend["FALLER"]  (I11: opposite trend signs)
- ratings["RISER"] > ratings["FALLER"]  (recency makes the current stronger look better)
- week_params(RISER, 1).attack ≈ week_params(FALLER, 6).attack  (symmetric setup verification)

Invariants stressed: I11 (momentum trend output).
"""

from generator.simulate import week_params
from models.bespoke import rate_weekly
from scenarios.builders import build_s11_momentum


def test_s11_trend_signs_i11():
    """I11: RISER trend positive, FALLER trend negative."""
    dataset, meta = build_s11_momentum()
    result = rate_weekly(dataset.games)
    trend = result.trend

    assert trend["RISER"] > 0, f"RISER trend should be positive, got {trend['RISER']:.4f}"
    assert trend["FALLER"] < 0, f"FALLER trend should be negative, got {trend['FALLER']:.4f}"


def test_s11_recency_makes_riser_rate_above_faller():
    """Recency weighting: the team that is currently stronger rates above the currently weaker."""
    dataset, meta = build_s11_momentum()
    result = rate_weekly(dataset.games)
    r = result.ratings

    assert r["RISER"] > r["FALLER"], (
        f"Expected RISER ({r['RISER']:.4f}) > FALLER ({r['FALLER']:.4f}) after recency weighting"
    )


def test_s11_symmetric_setup():
    """Verify the scenario is truly symmetric: RISER week-1 attack ≈ FALLER late-season attack."""
    dataset, meta = build_s11_momentum()
    teams_by_id = {t.id: t for t in dataset.ground_truth}
    riser = teams_by_id["RISER"]
    faller = teams_by_id["FALLER"]

    # Week 1 RISER attack should ≈ FALLER's late-season attack (n_weeks determined by meta).
    n_weeks = meta["n_weeks"]
    riser_w1_attack, _ = week_params(riser, 1)
    faller_late_attack, _ = week_params(faller, n_weeks)

    assert abs(riser_w1_attack - faller_late_attack) < 0.02, (
        f"Setup not symmetric: RISER w1 attack={riser_w1_attack:.3f}, "
        f"FALLER w{n_weeks} attack={faller_late_attack:.3f}"
    )
