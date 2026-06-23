"""Scenario 10 — Transitivity trap A>B>C>A (I8, I9).

A non-transitive cycle: A beats B, B beats C, C beats A, all by ~2 goals. Repeated many times
across weeks. The solver must find a fixed point (I9) even though no linear order satisfies all
games, and two runs must be byte-identical (I8). The ratings may come out approximately equal
(which is the correct answer for a symmetric cycle) or in some order — we do not assert which.

Invariants stressed: I8 (determinism), I9 (convergence — cycle must not diverge).
"""

import math

from models.bespoke import rate_weekly
from scenarios.builders import build_s10_transitivity_trap


def test_s10_solver_converges_no_divergence():
    """I9: the cycle must produce finite, well-defined ratings."""
    dataset, meta = build_s10_transitivity_trap()
    result = rate_weekly(dataset.games)
    r = result.ratings

    assert set(r) >= {"A", "B", "C"}
    for team in ("A", "B", "C"):
        assert math.isfinite(r[team]), f"Team {team} rating not finite: {r[team]}"


def test_s10_deterministic_i8():
    """I8: two runs on the same games give byte-identical ratings."""
    dataset, _ = build_s10_transitivity_trap()
    a = rate_weekly(dataset.games)
    b = rate_weekly(dataset.games)
    assert a.ratings == b.ratings


def test_s10_order_independent_i8():
    """I8: reversing input game order gives byte-identical ratings."""
    dataset, _ = build_s10_transitivity_trap()
    a = rate_weekly(dataset.games)
    b = rate_weekly(list(reversed(dataset.games)))
    assert a.ratings == b.ratings
