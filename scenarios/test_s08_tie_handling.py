"""Scenario 8 — Tie handling (I5).

T_WIN, T_TIE, T_LOSE each play the same opponents with the same margins, differing only in
whether their contested games end as wins, ties, or losses.

I5: ratings must order T_WIN > T_TIE > T_LOSE. Both gaps must be positive.
Additional constraint: the tie-vs-loss gap must be smaller than the win-vs-tie gap (a tie is
closer to a loss than a win — "no big bump" from tying, rule 2).

Invariants stressed: I5 (tie placement).
"""

from models.bespoke import rate_weekly
from scenarios.builders import build_s08_tie_handling


def test_s08_tie_ordering_i5():
    """I5: W > T > L in ratings."""
    dataset, meta = build_s08_tie_handling()
    result = rate_weekly(dataset.games)
    r = result.ratings

    r_win = r["T_WIN"]
    r_tie = r["T_TIE"]
    r_lose = r["T_LOSE"]

    assert r_win > r_tie, f"T_WIN ({r_win:.4f}) should be > T_TIE ({r_tie:.4f})"
    assert r_tie > r_lose, f"T_TIE ({r_tie:.4f}) should be > T_LOSE ({r_lose:.4f})"


def test_s08_tie_closer_to_loss_than_win():
    """'No big bump': the tie-vs-loss gap should be smaller than the win-vs-tie gap."""
    dataset, _ = build_s08_tie_handling()
    result = rate_weekly(dataset.games)
    r = result.ratings

    gap_win_tie = r["T_WIN"] - r["T_TIE"]
    gap_tie_lose = r["T_TIE"] - r["T_LOSE"]

    assert gap_tie_lose < gap_win_tie, (
        f"Tie should be closer to loss than win. "
        f"win-tie gap={gap_win_tie:.4f}, tie-lose gap={gap_tie_lose:.4f}"
    )
