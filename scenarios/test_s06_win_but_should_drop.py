"""Scenario 6 — Win-but-should-drop (I7).

T_UGLY wins all 8 games by exactly 1 goal (close margin, no bonus).
T_DOMINANT wins all 8 games by 4+ goals (big margin, full bonus) against the same opponents.

I7: bigger margins against the same opponent earns more. T_DOMINANT should rate above T_UGLY.
But the fairness floor holds: T_UGLY still rates above 0 (wins are positive even if close).

Invariants stressed: I7 (underperformance / margin signal — bigger beats same-record close-win).
"""

from models.bespoke import rate_weekly
from scenarios.builders import build_s06_win_but_should_drop


def test_s06_dominant_above_ugly():
    dataset, meta = build_s06_win_but_should_drop()
    result = rate_weekly(dataset.games)
    r = result.ratings

    dominant = r["T_DOMINANT"]
    ugly = r["T_UGLY"]
    assert dominant > ugly, (
        f"Expected T_DOMINANT ({dominant:.4f}) > T_UGLY ({ugly:.4f}): "
        f"margin signal (I7) should separate them. Full ratings: {r}"
    )


def test_s06_ugly_wins_are_positive():
    """The fairness floor: close wins still earn positive credit — only better wins earn more."""
    dataset, _ = build_s06_win_but_should_drop()
    result = rate_weekly(dataset.games)
    ugly = result.ratings["T_UGLY"]
    assert ugly > 0, (
        f"T_UGLY rating = {ugly:.4f} — close wins should still be positive (I1 floor)"
    )
