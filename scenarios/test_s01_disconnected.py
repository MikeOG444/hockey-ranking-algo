"""Scenario 1 — Disconnected clusters (I8, I9).

Two pods of 3 teams (A1–A3, B1–B3) play a full round-robin within their pod for ≥6 weeks.
Zero cross-pod games. The solver must converge and produce a finite rating for all 6 teams even
though there is no cross-pod evidence. Regularization (λ > 0) anchors the pods on a shared scale.

Invariants stressed: I8 (determinism), I9 (convergence — no free additive constant per pod).
"""

import math

from models.bespoke import rate_weekly
from scenarios.builders import build_s01_disconnected


def test_s01_converges_both_pods_finite():
    dataset, meta = build_s01_disconnected()
    result = rate_weekly(dataset.games)
    ratings = result.ratings

    # Six teams, one rating each.
    assert len(ratings) == 6, f"Expected 6 teams, got {len(ratings)}: {list(ratings)}"

    # All ratings finite (no nan/inf — regularization prevents the free-constant explosion).
    for team, r in ratings.items():
        assert math.isfinite(r), f"Rating for {team} is not finite: {r}"

    # Both pods represented.
    pod_a = [t for t in ratings if t.startswith("A")]
    pod_b = [t for t in ratings if t.startswith("B")]
    assert len(pod_a) == 3, f"Pod A has {len(pod_a)} teams"
    assert len(pod_b) == 3, f"Pod B has {len(pod_b)} teams"

    # Tiers populated for all 6.
    assert len(result.tiers) == 6


def test_s01_deterministic_i8():
    """I8: same games in reversed order produce byte-identical ratings."""
    dataset, _ = build_s01_disconnected()
    a = rate_weekly(dataset.games)
    b = rate_weekly(list(reversed(dataset.games)))
    assert a.ratings == b.ratings
