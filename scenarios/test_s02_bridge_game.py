"""Scenario 2 — Single bridge game (I8, I9).

Same two pods as S01, but exactly one cross-game (A2 vs B2 in week 3) connects the graph.
The bridge participants' per_game_attribution must contain a non-zero schedule_term for that game,
proving the cross-pod signal propagated. Solver must converge; ratings must differ from the
fully-disconnected case for at least the bridge participants.

Invariants stressed: I8 (determinism), I9 (convergence), I12 (attribution / schedule term).
"""

import math

from models.bespoke import rate_weekly
from scenarios.builders import build_s01_disconnected, build_s02_bridge_game


def test_s02_bridge_connects_pods():
    dataset, meta = build_s02_bridge_game()
    result = rate_weekly(dataset.games)

    # All 6 teams rated finitely.
    assert len(result.ratings) == 6
    for team, r in result.ratings.items():
        assert math.isfinite(r), f"{team} has non-finite rating: {r}"

    # The bridge game leaves a schedule_term trace in A2's and B2's attribution.
    a2_terms = [bd.schedule_term for bd in result.per_game_attribution.get("A2", [])]
    b2_terms = [bd.schedule_term for bd in result.per_game_attribution.get("B2", [])]
    assert any(t != 0.0 for t in a2_terms), "A2 should have a non-zero schedule term from the bridge"
    assert any(t != 0.0 for t in b2_terms), "B2 should have a non-zero schedule term from the bridge"


def test_s02_bridge_changes_ratings_vs_disconnected():
    """The bridge game must change A2's and B2's ratings relative to the fully-disconnected baseline."""
    ds_disconnected, _ = build_s01_disconnected()
    ds_bridge, _ = build_s02_bridge_game()

    r_disc = rate_weekly(ds_disconnected.games).ratings
    r_bridge = rate_weekly(ds_bridge.games).ratings

    # At least one bridge participant's rating must change when the bridge game is added.
    a2_changed = abs(r_bridge.get("A2", 0) - r_disc.get("A2", 0)) > 1e-6
    b2_changed = abs(r_bridge.get("B2", 0) - r_disc.get("B2", 0)) > 1e-6
    assert a2_changed or b2_changed, (
        f"Bridge game had no effect on A2 ({r_disc['A2']:.4f}->{r_bridge['A2']:.4f}) "
        f"or B2 ({r_disc['B2']:.4f}->{r_bridge['B2']:.4f})"
    )


def test_s02_deterministic_i8():
    """I8: byte-identical regardless of game input order."""
    dataset, _ = build_s02_bridge_game()
    a = rate_weekly(dataset.games)
    b = rate_weekly(list(reversed(dataset.games)))
    assert a.ratings == b.ratings
