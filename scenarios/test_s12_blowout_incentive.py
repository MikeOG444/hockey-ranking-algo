"""Scenario 12 — Blowout incentive (I3).

T_BLOWOUT wins all 8 games 8-0 (huge margin, 5+ bucket, max bonus).
T_CLOSE wins all 8 games 2-1 (close margin, 0 bonus) against the same opponents.

I3: bigger margins earn more → T_BLOWOUT > T_CLOSE.
The gap is bounded: the win_bonus schedule is diminishing (memo §1.2), so the max bonus gap
per game is win_bonus["5+"] - win_bonus["close"] = 1.0 - 0.0 = 1.0, scaled by (1 - lam).
The season-level gap should be below this ceiling.

Invariants stressed: I3 (blowout cap / diminishing margin bonus).
"""

from models.bespoke import BespokeParams, rate_weekly
from scenarios.builders import build_s12_blowout_incentive


def test_s12_blowout_above_close():
    """I3: larger margin earns a higher rating (directional)."""
    dataset, meta = build_s12_blowout_incentive()
    result = rate_weekly(dataset.games)
    r = result.ratings

    blowout = r["T_BLOWOUT"]
    close = r["T_CLOSE"]
    assert blowout > close, (
        f"Expected T_BLOWOUT ({blowout:.4f}) > T_CLOSE ({close:.4f}): "
        f"margin signal (I3) should separate them. Full ratings: {r}"
    )


def test_s12_gap_is_bounded():
    """I3 cap: the rating gap is bounded — blowout doesn't earn unboundedly more than close wins."""
    dataset, _ = build_s12_blowout_incentive()
    result = rate_weekly(dataset.games, lam=0.05)
    r = result.ratings

    p = BespokeParams()
    lam = 0.05
    # Max per-game bonus gap: win_bonus["5+"] - win_bonus["close"] = 1.0 - 0.0 = 1.0
    # Scaled by (1 - lam) ≈ 0.95; this is a per-game ceiling; over many games the season-avg gap
    # is compressed to < this. Use 2x as a generous bound (covers 8 games each, centering, etc.).
    max_gap = (p.win_bonus["5+"] - p.win_bonus["close"]) * (1 - lam) * 2
    actual_gap = r["T_BLOWOUT"] - r["T_CLOSE"]

    assert actual_gap < max_gap, (
        f"Rating gap {actual_gap:.4f} exceeds bounded ceiling {max_gap:.4f}: "
        f"blowout bonus not diminishing as expected."
    )
