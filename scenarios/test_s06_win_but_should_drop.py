"""Scenario 6 — Win-but-should-drop (I7).

T_UGLY wins all 8 games by exactly 1 goal (close margin, no bonus).
T_DOMINANT wins all 8 games by 4+ goals (big margin, full bonus) against the same opponents.

I7: bigger margins against the same opponent earns more. T_DOMINANT should rate above T_UGLY.

The fairness floor under surprise-centered credit (TASK-17) is "a win is not a loss": a win never
lowers you *relative to the opponent you beat*. So T_UGLY must rate above SHARED_OPP (the team it beats
every week) — but it need NOT rate above the league mean. This is the deliberate change: padding close
wins over the weakest team no longer makes you above-average (the old `base=3` floor guaranteed a
positive rating for any winner; surprise-centering correctly makes an *expected* win ~neutral).

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


def test_s06_ugly_wins_keep_you_above_the_team_you_beat():
    """The surprise-centered floor (TASK-17, 'a win is not a loss'): T_UGLY beats SHARED_OPP every
    week, so it must rate above SHARED_OPP — a win never lowers you relative to the team you beat. It
    need NOT be above the league mean: an expected win over the weakest team is ~neutral, so padding
    soft wins does not buy an above-average rating (the Woodbridge principle, on a unit scenario)."""
    dataset, _ = build_s06_win_but_should_drop()
    result = rate_weekly(dataset.games)
    r = result.ratings
    assert r["T_UGLY"] > r["SHARED_OPP"], (
        f"T_UGLY ({r['T_UGLY']:.4f}) must rate above SHARED_OPP ({r['SHARED_OPP']:.4f}) — "
        f"the team it beats every week (the 'a win is not a loss' floor). Full ratings: {r}"
    )
